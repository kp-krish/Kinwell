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
            hits = await _sm_search(person["_id"], limit)
            if hits:
                return hits
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


def _text_of(item: dict) -> str:
    for key in ("memory", "chunk", "content"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for k2 in ("memory", "content", "text"):
                if isinstance(v.get(k2), str) and v[k2].strip():
                    return v[k2].strip()
    return ""


async def _sm_search(person_id: str, limit: int) -> list[str]:
    """Supermemory API v5: namespace in the path, one namespace per person."""
    body = {"query": "air conditioning status, heat symptoms, who was notified, recent heat check-ins",
            "limit": limit, "searchMode": "hybrid"}
    async with httpx.AsyncClient(timeout=6) as c:
        r = await c.post(f"{SM_BASE}/ns/{_tag(person_id)}/search", json=body, headers=_headers())
        r.raise_for_status()
        data = r.json()
    out: list[str] = []
    for item in data.get("results", []):
        text = _text_of(item)
        if text and text not in out:
            out.append(text)
    return out[:limit]


async def _sm_add(person_id: str, summary: str) -> None:
    body = {"content": summary, "dreaming": "instant"}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{SM_BASE}/ns/{_tag(person_id)}/document", json=body, headers=_headers())
        r.raise_for_status()
        log.info("supermemory saved for %s: %s", person_id, r.json().get("status"))
