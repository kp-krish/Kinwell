"""Per-person call memory.

Supermemory (one containerTag per person) when SUPERMEMORY_API_KEY is set;
otherwise falls back to summaries of the person's recent check-ins in the store.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx

from . import config
from .store import get_store

log = logging.getLogger("memory")

SM_BASE = "https://api.supermemory.ai"
PHX = dt.timezone(dt.timedelta(hours=-7))


def _tag(person_id: str) -> str:
    return f"resident_{person_id}"


async def recall(person: dict, limit: int = 5) -> list[str]:
    if config.SUPERMEMORY_API_KEY:
        try:
            return await _sm_search(person["_id"], limit)
        except Exception:
            log.exception("supermemory search failed; using local fallback")
    return await _local_recall(person, limit)


async def remember(person: dict, summary: str) -> None:
    if not summary:
        return
    if config.SUPERMEMORY_API_KEY:
        try:
            await _sm_add(person["_id"], summary)
        except Exception:
            log.exception("supermemory add failed")


async def _local_recall(person: dict, limit: int) -> list[str]:
    rows = await get_store().find("checkins", {"resident_id": person["_id"], "call_status": "completed"},
                                  sort="started_at", limit=limit)
    out = []
    for r in rows:
        note = (r.get("case_note") or {}).get("memory_summary")
        started = r.get("started_at")
        when = (started.astimezone(PHX).strftime("%I:%M %p").lstrip("0")
                if hasattr(started, "astimezone") else "")
        if note:
            out.append(f"{when}: {note}")
            continue
        bits = []
        if r.get("ac_working") == "no":
            bits.append("said their AC was not working")
        if r.get("symptoms"):
            bits.append("reported " + ", ".join(r["symptoms"]))
        if r.get("water") == "no":
            bits.append("had not been drinking water")
        if bits:
            out.append(f"Earlier call ({when}): " + "; ".join(bits))
    return out


# --- Supermemory REST. Endpoint shapes per their docs; verified against the live API at runtime. ---

def _headers() -> dict:
    return {"Authorization": f"Bearer {config.SUPERMEMORY_API_KEY}", "Content-Type": "application/json"}


async def _sm_search(person_id: str, limit: int) -> list[str]:
    body = {"q": "AC status, health symptoms, who was notified, recent heat check-ins",
            "containerTags": [_tag(person_id)], "limit": limit}
    async with httpx.AsyncClient(timeout=6) as c:
        r = await c.post(f"{SM_BASE}/v3/search", json=body, headers=_headers())
        r.raise_for_status()
        data = r.json()
    out = []
    for item in data.get("results", [])[:limit]:
        text = item.get("memory") or item.get("content") or ""
        if not text and item.get("chunks"):
            text = item["chunks"][0].get("content", "")
        if text:
            out.append(text.strip())
    return out


async def _sm_add(person_id: str, summary: str) -> None:
    body = {"content": summary, "containerTags": [_tag(person_id)]}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{SM_BASE}/v3/documents", json=body, headers=_headers())
        r.raise_for_status()
