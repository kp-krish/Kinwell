"""Tools the voice agent can call, and their handlers.

The model only extracts facts through these tools. Escalation decisions are
made in rules.py, in plain code.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field

from . import rules, scheduler
from .sonic import ToolSpec
from .store import get_store, now

log = logging.getLogger("tools")

TOOL_SPECS = [
    ToolSpec("record_checkin", "Save the answers from this check-in. Always write the values in English, "
             "even when the conversation is in another language.", {
        "type": "object",
        "properties": {
            "ac_working": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"],
                           "description": "Is their air conditioning working (residents)."},
            "indoor_heat": {"type": "string", "description": "How hot it feels inside, in their words."},
            "water": {"type": "string", "enum": ["yes", "no", "unknown"],
                      "description": "Have they been drinking water (residents: today; crews: last hour)."},
            "rest_break": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"],
                           "description": "Crews: shade or rest break since last check-in."},
            "symptoms": {"type": "array", "items": {"type": "string"},
                         "description": "Symptoms they reported, e.g. dizziness, headache. Empty if none."},
            "coworker_concern": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"]},
            "heat_working": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"],
                             "description": "Cold-weather calls: is their home heat working."},
            "indoor_temp": {"type": "string", "description": "Cold-weather calls: how warm it is inside, in their words or degrees."},
            "power_on": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"],
                         "description": "Cold-weather calls: do they have power and gas or fuel for heat."},
            "unsafe_heating": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"],
                               "description": "Cold-weather calls: using an oven, stove, grill or generator indoors for heat."},
            "notes": {"type": "string", "description": "Anything else safety-relevant they said."},
        },
        "required": ["symptoms"],
    }),
    ToolSpec("flag_risk", "Raise a risk flag. Use level 'emergency' for heat-stroke signs "
             "(confusion, fainting, hot dry skin, vomiting, chest pain, coworker in trouble); "
             "'warning' for AC failure, dizziness, headache, no water, or no rest.", {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": ["warning", "emergency"]},
            "reason": {"type": "string", "description": "Short reason in plain English words."},
        },
        "required": ["level", "reason"],
    }),
    ToolSpec("find_cooling_center", "Find the nearest open cooling center or rest point with today's hours.", {
        "type": "object", "properties": {}, "required": [],
    }),
    ToolSpec("find_ac_assistance", "Find an AC repair or replacement assistance program.", {
        "type": "object", "properties": {}, "required": [],
    }),
    ToolSpec("schedule_callback", "Book a follow-up call in N minutes.", {
        "type": "object",
        "properties": {
            "minutes": {"type": "integer", "description": "Minutes from now, 10 to 120."},
            "reason": {"type": "string"},
        },
        "required": ["minutes"],
    }),
    ToolSpec("notify_contact", "Look up who will be alerted (family, caseworker, supervisor) so you can tell the person.", {
        "type": "object", "properties": {}, "required": [],
    }),
    ToolSpec("end_call", "Hang up after you have said goodbye.", {
        "type": "object", "properties": {}, "required": [],
    }),
]


_BY_NAME = {t.name: t for t in TOOL_SPECS}

COLD_FLAG = ToolSpec("flag_risk", "Raise a risk flag. Use level 'emergency' for hypothermia, frostbite or carbon "
                     "monoxide signs (confusion, slurred speech, very drowsy, shivering that won't stop or has stopped, "
                     "white or gray numb skin, chest pain, headache with dizziness near a fuel-burning heater); "
                     "'warning' for heat not working, a cold home, no power or gas, an unsafe indoor heat source, "
                     "heavy shivering or numb fingers.", _BY_NAME["flag_risk"].schema)

COLD_EXTRA = [
    ToolSpec("find_warming_center", "Find the nearest open warming center with today's hours.", {
        "type": "object", "properties": {}, "required": [],
    }),
    ToolSpec("find_heating_assistance", "Find a heating repair or utility bill assistance program.", {
        "type": "object", "properties": {}, "required": [],
    }),
]

COLD_TOOL_SPECS = ([_BY_NAME["record_checkin"], COLD_FLAG] + COLD_EXTRA
                   + [_BY_NAME[n] for n in ("schedule_callback", "notify_contact", "end_call")])

CONSENT_TOOL_SPECS = [
    ToolSpec("record_consent", "Save whether the person agreed to receive check-in calls on dangerous heat or cold days.", {
        "type": "object",
        "properties": {
            "agreed": {"type": "boolean"},
            "notes": {"type": "string", "description": "Anything they asked or said about the calls, in English."},
        },
        "required": ["agreed"],
    }),
    _BY_NAME["end_call"],
]


def tools_for(purpose: str, hazard: str) -> list:
    if purpose == "consent":
        return CONSENT_TOOL_SPECS
    if hazard == "cold":
        return COLD_TOOL_SPECS
    return TOOL_SPECS


@dataclass
class CallContext:
    person: dict
    checkin_id: str
    call_sid: str = ""
    flags: list[dict] = field(default_factory=list)
    callback_booked: bool = False
    ended: bool = False
    end_refusals: int = 0
    hangup_cb: object = None  # async callable
    hazard: str = "heat"
    purpose: str = "checkin"


def _fmt_age(fetched_at) -> str:
    if not fetched_at:
        return "unknown"
    if isinstance(fetched_at, str):
        fetched_at = dt.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    mins = int((now() - fetched_at).total_seconds() // 60)
    if mins < 60:
        return f"{max(mins, 1)} minutes ago"
    return f"{mins // 60} hours ago"


async def handle_tool(ctx: CallContext, name: str, args: dict) -> dict:
    store = get_store()
    person = ctx.person

    if name == "record_checkin":
        keys = ("ac_working", "indoor_heat", "water", "rest_break", "coworker_concern", "notes",
                "heat_working", "indoor_temp", "power_on", "unsafe_heating")
        fields = {k: args[k] for k in keys if args.get(k) is not None}
        fields["symptoms"] = args.get("symptoms") or []
        await store.update("checkins", ctx.checkin_id, fields)
        return {"saved": True}

    if name == "flag_risk":
        level = args.get("level", "warning")
        reason_l = (args.get("reason") or "").lower()
        if (person.get("playbook") == "crew" and level == "warning"
                and any(w in reason_l for w in ("water", "rest", "shade", "break", "hydrat"))):
            # Crew privacy rule (in code): one missed water/shade break is a reminder, not a supervisor alert.
            return {"flagged": False, "action": "Not a warning for crews. Remind them to take a shade break and "
                                                "drink water in the next 15 minutes. The supervisor is NOT alerted."}
        flag = {"level": level, "reason": args.get("reason", ""), "at": now()}
        ctx.flags.append(flag)
        await store.update("checkins", ctx.checkin_id, {"flags": ctx.flags})
        if level == "emergency":
            # Heat-stroke signs: alert contacts immediately, during the call.
            asyncio.create_task(rules.escalate_now(person, ctx.checkin_id, flag["reason"], emergency=True))
            return {"flagged": True, "action": "Contacts are being alerted right now. Tell them to call 911 now."}
        contact = await rules.next_contact(person)
        if contact:
            return {"flagged": True, "contact_name": contact["name"], "contact_role": contact["role"],
                    "action": f"{contact['name']} ({contact['role']}) will be alerted when this call ends."}
        return {"flagged": True, "action": "The care team will be alerted when this call ends."}

    if name == "record_consent":
        agreed = bool(args.get("agreed"))
        await store.update("checkins", ctx.checkin_id, {"consent": agreed, "consent_notes": args.get("notes", "")})
        return {"saved": True, "agreed": agreed}

    if name in ("find_cooling_center", "find_warming_center"):
        rtype = "cooling_center" if name == "find_cooling_center" else "warming_center"
        lng, lat = person["location"]["coordinates"]
        r = await store.nearest_resource(lng, lat, rtype, max_m=40000)
        if not r:
            return {"found": False, "message": f"No open {rtype.replace('_', ' ')} found nearby in today's data. "
                                               "Suggest a friend or family member's warm home, or calling 2 1 1."}
        miles = round(r.get("distance_m", 0) / 1609.34, 1)
        return {
            "found": True, "name": r["name"], "address": r["address"],
            "hours_today": r.get("hours_today"), "distance_miles": miles,
            "notes": r.get("notes", ""), "data_fetched": _fmt_age(r.get("fetched_at")),
        }

    if name in ("find_ac_assistance", "find_heating_assistance"):
        rtype = "ac_program" if name == "find_ac_assistance" else "heat_program"
        rows = await store.find("resources", {"type": rtype}, limit=1)
        if not rows:
            return {"found": False}
        r = rows[0]
        return {"found": True, "name": r["name"], "eligibility": r.get("eligibility", "")}

    if name == "schedule_callback":
        minutes = max(10, min(int(args.get("minutes") or 30), 120))
        from . import escalation
        if escalation.enabled():
            # The Step Functions ladder owns warning follow-ups; only record what was promised.
            when = now() + dt.timedelta(minutes=minutes)
        else:
            when = await scheduler.schedule_checkin(person["_id"], minutes, args.get("reason", "follow-up"))
        ctx.callback_booked = True
        await store.update("checkins", ctx.checkin_id, {"callback_at": when})
        return {"scheduled": True, "minutes": minutes}

    if name == "notify_contact":
        contact = await rules.next_contact(person)
        if not contact:
            return {"contact": None}
        return {"name": contact["name"], "role": contact["role"]}

    if name == "end_call":
        # Guard in code: don't hang up before the check-in is recorded with real answers.
        checkin = await store.get("checkins", ctx.checkin_id) or {}
        if ctx.purpose == "consent":
            unanswered = [] if "consent" in checkin else ["whether it is okay to call (then call record_consent)"]
        else:
            must = (("whether their heat works", "heat_working"),) if ctx.hazard == "cold"                 else (("drinking water", "water"),)
            unanswered = [q for q, k in must if checkin.get(k) in (None, "unknown")]
            if "symptoms" not in checkin:
                unanswered.append("symptoms")
        emergency = any(f.get("level") == "emergency" for f in ctx.flags)
        if unanswered and not emergency and ctx.end_refusals < 2:
            ctx.end_refusals += 1
            then = "" if ctx.purpose == "consent" else " Then call record_checkin, say goodbye, and call end_call."
            return {"ok": False, "error": "Do not hang up yet. Ask about: " + ", ".join(unanswered) + "." + then}
        ctx.ended = True
        if ctx.hangup_cb:
            asyncio.create_task(ctx.hangup_cb())
        return {"ok": True}

    return {"error": f"unknown tool {name}"}
