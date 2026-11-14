"""Gemini case notes. No-op until GEMINI_API_KEY is set."""
from __future__ import annotations

import logging

from . import config

log = logging.getLogger("notes")


async def case_note(person: dict, transcript: list[dict], result: dict) -> dict | None:
    if not config.GEMINI_API_KEY:
        return None
    return None  # implemented once the Gemini key is available
