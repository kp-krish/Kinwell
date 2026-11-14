"""Minimal Twilio REST helpers (no SDK needed)."""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

import httpx

from . import config

log = logging.getLogger("twilio")


def _base() -> str:
    return f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}"


def _auth() -> tuple[str, str]:
    return (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


async def create_call(to: str, *, url: str | None = None, twiml: str | None = None,
                      status_callback: str | None = None, timeout_s: int = 25,
                      detect_machine: bool = False) -> dict:
    data = {"To": to, "From": config.TWILIO_PHONE_NUMBER, "Timeout": str(timeout_s)}
    if detect_machine:
        # Twilio answering-machine detection: AnsweredBy is passed to the voice webhook.
        data["MachineDetection"] = "Enable"
        data["MachineDetectionTimeout"] = "8"
    if url:
        data["Url"] = url
    if twiml:
        data["Twiml"] = twiml
    if status_callback:
        data["StatusCallback"] = status_callback
        data["StatusCallbackEvent"] = "completed"
        data["StatusCallbackMethod"] = "POST"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{_base()}/Calls.json", data=data, auth=_auth())
    if r.status_code >= 300:
        log.error("create_call failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    return r.json()


async def hangup(call_sid: str) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(f"{_base()}/Calls/{call_sid}.json", data={"Status": "completed"}, auth=_auth())


def say_twiml(message: str, voice: str = "Polly.Joanna", repeat: int = 2) -> str:
    msg = escape(message)
    says = "".join(f'<Say voice="{voice}">{msg}</Say><Pause length="1"/>' for _ in range(repeat))
    return f"<Response>{says}</Response>"


async def notify_by_voice(to: str, message: str) -> str | None:
    """Call a contact and read them an alert. Returns call SID."""
    if not to:
        return None
    res = await create_call(to, twiml=say_twiml(message))
    return res.get("sid")
