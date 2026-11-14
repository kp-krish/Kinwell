"""Escalation rules, in plain code so outcomes are predictable and auditable.

The model never decides who gets alerted; it only reports facts via tools.
"""
from __future__ import annotations

import logging

from . import scheduler, twilio_api
from .playbooks import PLAYBOOKS
from .store import get_store, now

log = logging.getLogger("rules")

WARNING_SYMPTOMS = {"dizziness", "dizzy", "headache", "nausea", "cramps", "tired", "weak", "lightheaded"}


async def contacts_for(person: dict) -> list[dict]:
    rows = await get_store().find("contacts", {"resident_id": person["_id"]})
    roles = PLAYBOOKS[person.get("playbook", "resident")]["escalation_roles"]
    rows = [r for r in rows if r.get("role") in roles]
    return sorted(rows, key=lambda r: r.get("escalation_order", 99))


async def first_contact(person: dict) -> dict | None:
    rows = await contacts_for(person)
    return rows[0] if rows else None


async def _warning_alerts_today(person: dict) -> int:
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await get_store().find("alerts", {"resident_id": person["_id"], "level": "warning"})
    return sum(1 for r in rows if r.get("created_at") and r["created_at"] >= start)


async def next_contact(person: dict) -> dict | None:
    """Ladder: the first warning today goes to contact 1, a still-bad follow-up to contact 2, etc."""
    rows = await contacts_for(person)
    if not rows:
        return None
    step = await _warning_alerts_today(person)
    return rows[min(step, len(rows) - 1)]


def evaluate(person: dict, checkin: dict) -> dict:
    """Return {'level': 'clear'|'warning'|'emergency', 'reasons': [...]} from recorded facts."""
    reasons: list[str] = []
    flags = checkin.get("flags") or []
    if any(f.get("level") == "emergency" for f in flags):
        return {"level": "emergency", "reasons": [f["reason"] for f in flags if f.get("level") == "emergency"]}
    reasons += [f["reason"] for f in flags if f.get("level") == "warning"]
    if checkin.get("ac_working") == "no":
        reasons.append("AC not working")
    if checkin.get("water") == "no":
        reasons.append("no water")
    if person.get("playbook") == "crew" and checkin.get("rest_break") == "no":
        reasons.append("no shade or rest break")
    if checkin.get("coworker_concern") == "yes":
        reasons.append("coworker may be unwell")
    syms = [s.lower() for s in checkin.get("symptoms") or []]
    if syms:
        reasons.append("symptoms: " + ", ".join(syms))
    reasons = list(dict.fromkeys(reasons))
    return {"level": "warning" if reasons else "clear", "reasons": reasons}


def _alert_message(person: dict, reason: str, emergency: bool) -> str:
    name = person.get("name", "the person")
    if emergency:
        return (f"This is an urgent automated HeatCheck alert. During a heat check-in call, {name} "
                f"showed possible heat-stroke signs: {reason}. They were told to call 911. "
                f"Please check on {name} immediately.")
    return (f"This is an automated HeatCheck alert about {name}. During today's heat check-in: {reason}. "
            f"Please check on them. A follow-up call is scheduled.")


async def _write_alert(person: dict, checkin_id: str | None, level: str, reason: str, notified: list[str]) -> str:
    return await get_store().insert("alerts", {
        "resident_id": person["_id"], "resident_name": person.get("name"),
        "playbook": person.get("playbook"), "checkin_id": checkin_id,
        "level": level, "reason": reason, "notified": notified,
        "created_at": now(), "acknowledged_by": None, "resolved_at": None,
    })


async def escalate_now(person: dict, checkin_id: str | None, reason: str, emergency: bool) -> None:
    """Emergency: call every escalation contact now. Warning: call the next contact on the ladder."""
    if emergency:
        targets = await contacts_for(person)
    else:
        nxt = await next_contact(person)
        targets = [nxt] if nxt else []
    notified = []
    for c in targets:
        try:
            await twilio_api.notify_by_voice(c["phone"], _alert_message(person, reason, emergency))
            notified.append(f"{c['name']} ({c['role']})")
        except Exception:
            log.exception("notify %s failed", c.get("name"))
    await _write_alert(person, checkin_id, "emergency" if emergency else "warning", reason, notified)
    log.info("escalated %s level=%s notified=%s", person["_id"], "emergency" if emergency else "warning", notified)


async def after_call(person: dict, checkin_id: str, callback_booked: bool) -> dict:
    """Apply rules once the call has ended and the tools have written the facts."""
    store = get_store()
    checkin = await store.get("checkins", checkin_id) or {}
    result = evaluate(person, checkin)
    await store.update("checkins", checkin_id, {"risk_level": result["level"], "risk_reasons": result["reasons"]})

    if result["level"] == "emergency":
        pass  # contacts were already alerted during the call
    elif result["level"] == "warning":
        ladder_len = len(await contacts_for(person))
        step = await _warning_alerts_today(person)
        await escalate_now(person, checkin_id, "; ".join(result["reasons"]), emergency=False)
        # Book one follow-up per ladder rung; once every contact has been alerted,
        # stop calling and leave the open alert for a human on the dashboard.
        if not callback_booked and step + 1 < max(ladder_len, 1):
            await scheduler.schedule_checkin(person["_id"], 30, "warning-sign follow-up")
        await store.update("checkins", checkin_id, {"ladder_step": step + 1})
    elif person.get("playbook") == "crew":
        await _crew_consecutive_check(person)
    return result


async def _crew_consecutive_check(person: dict) -> None:
    """Crew rule: two 'no' answers on water or rest in a row -> supervisor alert."""
    rows = await get_store().find("checkins", {"resident_id": person["_id"], "call_status": "completed"},
                                  sort="started_at", limit=2)
    if len(rows) == 2 and all(r.get("water") == "no" or r.get("rest_break") == "no" for r in rows):
        await escalate_now(person, rows[0]["_id"], "two check-ins in a row without water or rest", emergency=False)


async def on_no_answer(person: dict, checkin_id: str, attempt: int) -> None:
    """Missed call: retry per playbook, then walk the escalation ladder."""
    pb = PLAYBOOKS[person.get("playbook", "resident")]
    await get_store().update("checkins", checkin_id, {"call_status": "no_answer", "risk_level": "no_answer"})
    if attempt < pb["max_retries"]:
        await scheduler.schedule_checkin(person["_id"], pb["retry_minutes"], "retry after no answer",
                                         attempt=attempt + 1)
    else:
        await escalate_now(person, checkin_id,
                           f"did not answer {attempt + 1} check-in calls", emergency=False)
