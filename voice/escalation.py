"""Bridge between the voice server and the Step Functions escalation ladder.

When STATE_MACHINE_ARN is set (deployed), warnings and exhausted retries start an
execution of the heatcheck-escalation state machine, which alerts one contact per
rung, waits, places a follow-up call and decides from the result. Follow-up calls
placed by the state machine carry a task token; when they end, the result goes
back to Step Functions instead of escalating again here.

Without STATE_MACHINE_ARN (local dev), rules.py falls back to in-process timers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

log = logging.getLogger("escalation")

STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")
INFRA_REGION = os.environ.get("INFRA_REGION", "us-east-2")
FOLLOWUP_MINUTES = 30


def enabled() -> bool:
    return bool(STATE_MACHINE_ARN)


def _sfn():
    import boto3
    return boto3.client("stepfunctions", region_name=INFRA_REGION)


def wait_seconds(minutes: int = FOLLOWUP_MINUTES) -> int:
    from . import scheduler
    return max(10, int(minutes * scheduler.SECONDS_PER_MINUTE))


async def start_ladder(person: dict, checkin_id: str, level: str, reasons: list[str], findings: str = "") -> str | None:
    payload = {
        "person_id": person["_id"], "person_name": person.get("name"), "checkin_id": checkin_id,
        "level": level, "reasons": reasons, "findings": findings, "step": 0,
        "wait_seconds": wait_seconds(),
    }
    name = re.sub(r"[^A-Za-z0-9_-]", "-", f"{person['_id']}-{checkin_id[:10]}")[:80]
    res = await asyncio.to_thread(_sfn().start_execution, stateMachineArn=STATE_MACHINE_ARN,
                                  name=name, input=json.dumps(payload))
    log.info("ladder started for %s: %s", person["_id"], res["executionArn"])
    return res["executionArn"]


async def report_followup(task_token: str, level: str, reasons: list[str]) -> None:
    out = json.dumps({"level": level, "reasons": reasons})
    try:
        await asyncio.to_thread(_sfn().send_task_success, taskToken=task_token, output=out)
        log.info("follow-up result sent to Step Functions: %s", level)
    except Exception:
        log.exception("send_task_success failed")
