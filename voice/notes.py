"""Gemini: structured case notes per call and a ranked briefing of who needs a human call.

Gemini does text work after the call. Sonic handles live voice. Escalation stays in rules.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from pydantic import BaseModel, Field

from . import config

log = logging.getLogger("notes")

MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash"] if m]


class CaseNote(BaseModel):
    summary: str = Field(description="Two plain-language sentences for a caseworker.")
    ac_status: str = Field(description="working | broken | unknown | not_applicable")
    symptoms: list[str]
    needs_human_today: bool
    reason: str = Field(description="One line: why a human should or need not call today.")
    memory_summary: str = Field(description="One short sentence of safety facts to remember for the next call, "
                                            "e.g. 'AC broken since morning; felt dizzy; daughter Maria notified.'")


class BriefingItem(BaseModel):
    resident_id: str
    name: str
    priority: int = Field(description="1 = most urgent")
    reason: str = Field(description="One line a caseworker can act on.")


class Briefing(BaseModel):
    headline: str = Field(description="e.g. 'Of 40 calls, three people need a human today.'")
    items: list[BriefingItem]


NOTE_PROMPT = """You write case notes for a heat-safety check-in program in Maricopa County, Arizona.
Given a phone check-in transcript and the facts the system recorded, fill the schema.
Be factual and brief. Never diagnose. Refer to the person by first name rather than pronouns. Use plain language a caseworker can scan in seconds.
needs_human_today is true if there were warning signs (AC out, symptoms, no water, no rest) or the call was unclear."""

BRIEFING_PROMPT = """You prepare the briefing for heat-safety caseworkers and crew supervisors.
Given today's check-in results, rank ONLY the people who need a human call today, most urgent first.
Emergencies first, then symptoms, then AC failures and missed calls. One actionable line each.
The headline states how many calls were made and how many people need a human."""


def _client():
    from google import genai
    return genai.Client(api_key=config.GEMINI_API_KEY, http_options={"timeout": 20000})


def _generate(prompt: str, content: str, schema):
    client = _client()
    last = None
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model, contents=[prompt, content],
                config={"response_mime_type": "application/json", "response_schema": schema})
            return json.loads(resp.text), model
        except Exception as e:  # model unavailable or rate-limited: try the next one
            last = e
            log.warning("gemini %s failed: %s", model, e)
    raise last


async def case_note(person: dict, transcript: list[dict], result: dict) -> dict | None:
    if not config.GEMINI_API_KEY:
        return None
    lines = "\n".join(f"{t['role']}: {t['text']}" for t in transcript if t.get("text", "").strip())
    content = (f"Person: {person.get('name')} ({person.get('playbook')}), risk factors: "
               f"{', '.join(person.get('risk_factors') or [])}\n"
               f"Rules result: {result['level']} {result['reasons']}\n\nTranscript:\n{lines}")
    note, model = await asyncio.to_thread(_generate, NOTE_PROMPT, content, CaseNote)
    note["model"] = model
    return note


async def briefing(checkins: list[dict]) -> dict:
    rows = []
    for c in checkins:
        rows.append({
            "resident_id": c.get("resident_id"), "name": c.get("resident_name"),
            "playbook": c.get("playbook"), "status": c.get("call_status"),
            "risk_level": c.get("risk_level"), "reasons": c.get("risk_reasons"),
            "note": (c.get("case_note") or {}).get("summary"),
        })
    data, model = await asyncio.to_thread(_generate, BRIEFING_PROMPT, json.dumps(rows, default=str), Briefing)
    data["model"] = model
    data["calls"] = len(rows)
    return data
