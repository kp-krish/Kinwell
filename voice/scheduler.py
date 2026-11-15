"""Schedules follow-up check-in calls (retries after no answer, crew shift check-ins).

At most ONE pending call per person: booking a new one replaces the old timer, so
retries, crew check-ins and callbacks can never stack up into several calls.
Warning-sign follow-ups are owned by the Step Functions ladder when it is deployed
(see escalation.py), not by this module.

DEMO_SECONDS_PER_MINUTE compresses time for the live demo (4 => a "30 minute"
callback fires in 2 minutes).
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

_pending: dict[str, asyncio.Task] = {}


def cancel(person_id: str) -> None:
    task = _pending.pop(person_id, None)
    if task and not task.done():
        task.cancel()
        log.info("cancelled pending call for %s", person_id)


async def schedule_checkin(person_id: str, minutes: int, reason: str, attempt: int = 0,
                         purpose: str = "checkin", context: dict | None = None) -> dt.datetime:
    when = now() + dt.timedelta(minutes=minutes)
    delay = minutes * SECONDS_PER_MINUTE
    cancel(person_id)  # one pending call per person
    log.info("callback for %s in %s min (%ss real): %s", person_id, minutes, delay, reason)

    async def fire():
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        _pending.pop(person_id, None)
        if place_call:
            try:
                await place_call(person_id, attempt=attempt, reason=reason, purpose=purpose, context=context)
            except Exception:
                log.exception("scheduled call failed")

    _pending[person_id] = asyncio.create_task(fire())
    return when
