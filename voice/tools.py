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
    ToolSpec("record_checkin", "Save the answers from this check-in.", {
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
            "notes": {"type": "string", "description": "Anything else safety-relevant they said."},
        },
        "required": ["water", "symptoms"],
    }),
    ToolSpec("flag_risk", "Raise a risk flag. Use level 'emergency' for heat-stroke signs "
             "(confusion, fainting, hot dry skin, vomiting, chest pain, coworker in trouble); "
             "'warning' for AC failure, dizziness, headache, no water, or no rest.", {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": ["warning", "emergency"]},
            "reason": {"type": "string", "description": "Short reason in plain words."},
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


@dataclass
class CallContext:
    person: dict
    checkin_id: str
    call_sid: str = ""
    flags: list[dict] = field(default_factory=list)
    callback_booked: bool = False
    ended: bool = False
    hangup_cb: object = None  # async callable


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
        fields = {k: args.get(k) for k in ("ac_working", "indoor_heat", "water", "rest_break",
                                           "coworker_concern", "notes")}
        fields["symptoms"] = args.get("symptoms") or []
        await store.update("checkins", ctx.checkin_id, fields)
        return {"saved": True}

    if name == "flag_risk":
        level = args.get("level", "warning")
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

    if name == "find_cooling_center":
        lng, lat = person["location"]["coordinates"]
        r = await store.nearest_resource(lng, lat, "cooling_center")
        if not r:
            return {"found": False, "message": "No open cooling center found nearby in today's data."}
        miles = round(r.get("distance_m", 0) / 1609.34, 1)
        return {
            "found": True, "name": r["name"], "address": r["address"],
            "hours_today": r.get("hours_today"), "distance_miles": miles,
            "notes": r.get("notes", ""), "data_fetched": _fmt_age(r.get("fetched_at")),
        }

    if name == "find_ac_assistance":
        rows = await store.find("resources", {"type": "ac_program"}, limit=1)
        if not rows:
            return {"found": False}
        r = rows[0]
        return {"found": True, "name": r["name"], "eligibility": r.get("eligibility", "")}

    if name == "schedule_callback":
        minutes = max(10, min(int(args.get("minutes") or 30), 120))
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
        ctx.ended = True
        if ctx.hangup_cb:
            asyncio.create_task(ctx.hangup_cb())
        return {"ok": True}

    return {"error": f"unknown tool {name}"}
