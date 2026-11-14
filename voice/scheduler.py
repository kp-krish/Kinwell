"""Schedules follow-up check-in calls.

Local/dev: an in-process asyncio timer. The deployed version hands this to
EventBridge Scheduler / Step Functions (see infra/). DEMO_SECONDS_PER_MINUTE
compresses time for the live demo (e.g. 2 => a "30 minute" callback fires in 60 s).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os

from .store import now

log = logging.getLogger("scheduler")

SECONDS_PER_MINUTE = float(os.environ.get("DEMO_SECONDS_PER_MINUTE", "60"))

# Set by app.py to avoid a circular import: async fn(person_id, attempt, reason)
place_call = None


async def schedule_checkin(person_id: str, minutes: int, reason: str, attempt: int = 0) -> dt.datetime:
    when = now() + dt.timedelta(minutes=minutes)
    delay = minutes * SECONDS_PER_MINUTE
    log.info("callback for %s in %s min (%ss real): %s", person_id, minutes, delay, reason)

    async def fire():
        await asyncio.sleep(delay)
        if place_call:
            try:
                await place_call(person_id, attempt=attempt, reason=reason)
            except Exception:
                log.exception("scheduled call failed")

    asyncio.create_task(fire())
    return when
