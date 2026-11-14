"""Escalation rules, in plain code so outcomes are predictable and auditable.

The model never decides who gets alerted; it only reports facts via tools.
"""
from __future__ import annotations

import logging

from . import escalation, scheduler, twilio_api
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
    flag_reasons = [f["reason"] for f in flags if f.get("level") == "warning"]
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
    # Recorded facts are the source of truth; the agent's own flag wording is used only
    # when no recorded fact explains the warning (avoids "AC broken; AC still off; AC not working").
    if not reasons:
        reasons = flag_reasons
    reasons = list(dict.fromkeys(reasons))
    return {"level": "warning" if reasons else "clear", "reasons": reasons}


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def spoken_findings(person: dict, checkin: dict) -> str:
    """Turn recorded facts into a sentence that sounds natural when read aloud."""
    who = person.get("first_name") or "they"
    is_, has = ("are", "have") if who == "they" else ("is", "has")
    parts = []
    if checkin.get("ac_working") == "no":
        parts.append("the air conditioning is not working")
    syms = [s.lower().strip() for s in checkin.get("symptoms") or []]
    if syms:
        parts.append(f"{who} {is_} feeling " + _join(syms).replace("dizziness", "dizzy"))
    if checkin.get("water") == "no":
        parts.append(f"{who} {has} not been drinking water")
    if person.get("playbook") == "crew" and checkin.get("rest_break") == "no":
        parts.append(f"{who} {has} not had a shade or rest break")
    if checkin.get("coworker_concern") == "yes":
        parts.append("a coworker may be unwell")
    return _join(parts)


def _alert_message(person: dict, reason: str, emergency: bool, findings: str = "") -> str:
    name = person.get("name", "the person")
    first = person.get("first_name") or name
    if emergency:
        return (f"This is an urgent automated alert from HeatCheck. During a heat check-in call just now, "
                f"{name} showed possible signs of heat stroke: {reason}. {first} was told to call 9 1 1. "
                f"Please check on {first} right away.")
    if findings:
        what = f"On today's heat check-in call, {first} told us that {findings}."
    else:
        what = f"Today's heat check-in found that {reason}."
    return (f"Hello, this is an automated alert from HeatCheck about {name}. {what} "
            f"Please check on {first} soon.")


async def _write_alert(person: dict, checkin_id: str | None, level: str, reason: str, notified: list[str]) -> str:
    return await get_store().insert("alerts", {
        "resident_id": person["_id"], "resident_name": person.get("name"),
        "playbook": person.get("playbook"), "checkin_id": checkin_id,
        "level": level, "reason": reason, "notified": notified,
        "created_at": now(), "acknowledged_by": None, "resolved_at": None,
    })


async def escalate_now(person: dict, checkin_id: str | None, reason: str, emergency: bool,
                       findings: str = "", rung: int | None = None) -> list[str]:
    """Emergency: call every escalation contact now. Warning: call one contact on the ladder
    (the given rung when Step Functions drives it, otherwise the next one today)."""
    if emergency:
        targets = await contacts_for(person)
    elif rung is not None:
        ladder = await contacts_for(person)
        targets = [ladder[rung]] if rung < len(ladder) else []
    else:
        nxt = await next_contact(person)
        targets = [nxt] if nxt else []
    notified = []
    for c in targets:
        try:
            await twilio_api.notify_by_voice(c["phone"], _alert_message(person, reason, emergency, findings))
            notified.append(f"{c['name']} ({c['role']})")
        except Exception:
            log.exception("notify %s failed", c.get("name"))
    await _write_alert(person, checkin_id, "emergency" if emergency else "warning", reason, notified)
    log.info("escalated %s level=%s notified=%s", person["_id"], "emergency" if emergency else "warning", notified)
    return notified


async def after_call(person: dict, checkin_id: str, callback_booked: bool) -> dict:
    """Apply rules once the call has ended and the tools have written the facts."""
    store = get_store()
    checkin = await store.get("checkins", checkin_id) or {}
    has_facts = "water" in checkin or "symptoms" in checkin or checkin.get("flags")
    if not has_facts:
        # No answers were recorded (voicemail, dropped call, hung up early). Unconfirmed is never "safe".
        await on_no_answer(person, checkin_id, checkin.get("attempt", 0), why="call ended before check-in answers")
        return {"level": "no_answer", "reasons": ["call ended before check-in answers"]}
    result = evaluate(person, checkin)
    await store.update("checkins", checkin_id, {"risk_level": result["level"], "risk_reasons": result["reasons"]})

    if checkin.get("task_token"):
        # Follow-up call placed by the Step Functions ladder: it decides the next step.
        await escalation.report_followup(checkin["task_token"], result["level"], result["reasons"])
        return result
    if result["level"] == "warning" and escalation.enabled():
        await escalation.start_ladder(person, checkin_id, "warning", result["reasons"],
                                      spoken_findings(person, checkin))
        return result

    if result["level"] == "emergency":
        pass  # contacts were already alerted during the call
    elif result["level"] == "warning":
        ladder_len = len(await contacts_for(person))
        step = await _warning_alerts_today(person)
        await escalate_now(person, checkin_id, "; ".join(result["reasons"]), emergency=False,
                           findings=spoken_findings(person, checkin))
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


async def on_no_answer(person: dict, checkin_id: str, attempt: int, why: str = "no answer") -> None:
    """Missed call (no answer, busy, voicemail, or ended before answers): retry per playbook,
    then walk the escalation ladder. Never treated as safe."""
    pb = PLAYBOOKS[person.get("playbook", "resident")]
    store = get_store()
    await store.update("checkins", checkin_id, {"call_status": "no_answer", "risk_level": "no_answer",
                                                "risk_reasons": [why]})
    checkin = await store.get("checkins", checkin_id) or {}
    if checkin.get("task_token"):
        await escalation.report_followup(checkin["task_token"], "no_answer", [why])
        return
    if attempt < pb["max_retries"]:
        await scheduler.schedule_checkin(person["_id"], pb["retry_minutes"], "retry after no answer",
                                         attempt=attempt + 1)
    else:
        first = person.get("first_name") or person.get("name", "they")
        reason = f"{first} did not answer {attempt + 1} check-in calls in a row"
        if escalation.enabled():
            await escalation.start_ladder(person, checkin_id, "no_answer", [reason])
        else:
            await escalate_now(person, checkin_id, reason, emergency=False)
