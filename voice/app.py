"""HeatCheck voice server: Twilio Media Streams <-> Amazon Nova 2 Sonic.

Run locally:  python -m uvicorn voice.app:app --port 8080
Twilio needs a public wss URL, so set PUBLIC_HOST (e.g. a cloudflared tunnel host).
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import logging
import time
from xml.sax.saxutils import quoteattr

from fastapi import FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from . import config, memory, rules, scheduler, twilio_api
from .audio import mulaw_to_pcm16, pcm16_to_mulaw
from .playbooks import VOICES
from .prompts import build_system_prompt, opening_nudge
from .sonic import SonicSession
from .store import calls_today, get_store, now
from .tools import TOOL_SPECS, CallContext, handle_tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="HeatCheck voice")

TRANSCRIPT_TTL_DAYS = 30
PHX = dt.timezone(dt.timedelta(hours=-7))  # Arizona has no DST


def public_base(request: Request | None = None) -> str:
    host = config.PUBLIC_HOST or (request.headers.get("host") if request else "")
    return host.replace("https://", "").replace("http://", "").rstrip("/")


# ---------------------------------------------------------------- placing calls

async def place_call(person_id: str, attempt: int = 0, reason: str = "scheduled check-in",
                     context: dict | None = None) -> dict:
    store = get_store()
    person = await store.get("residents", person_id)
    if not person:
        raise HTTPException(404, f"unknown person {person_id}")
    if not person.get("phone"):
        raise HTTPException(400, f"{person_id} has no phone number")
    if await calls_today(person_id) >= config.DAILY_CALL_CAP:
        log.warning("daily call cap reached for %s", person_id)
        return {"skipped": "daily call cap reached"}

    checkin_id = await store.insert("checkins", {
        "resident_id": person_id, "resident_name": person.get("name"),
        "playbook": person.get("playbook"), "started_at": now(), "attempt": attempt,
        "reason": reason, "call_status": "dialing", "context": context or {},
    })
    base = public_base()
    res = await twilio_api.create_call(
        person["phone"],
        url=f"https://{base}/twilio/voice?checkin_id={checkin_id}",
        status_callback=f"https://{base}/twilio/status?checkin_id={checkin_id}",
    )
    await store.update("checkins", checkin_id, {"call_sid": res.get("sid")})
    log.info("dialing %s checkin=%s sid=%s", person_id, checkin_id, res.get("sid"))
    return {"checkin_id": checkin_id, "call_sid": res.get("sid")}


scheduler.place_call = place_call


@app.get("/health")
async def health():
    return {"ok": True, "store": type(get_store()).__name__}


@app.post("/calls")
async def start_call(payload: dict):
    """Start a check-in call: {"person_id": "res_lopez", "high_f": 112, "alert_type": "NWS Extreme Heat Warning"}"""
    ctx = {k: payload[k] for k in ("high_f", "alert_type") if k in payload}
    return await place_call(payload["person_id"], reason=payload.get("reason", "manual"), context=ctx)


# ---------------------------------------------------------------- Twilio webhooks

@app.post("/twilio/voice")
async def twilio_voice(request: Request, checkin_id: str):
    ws_url = f"wss://{public_base(request)}/twilio/stream"
    twiml = (
        "<Response><Connect>"
        f"<Stream url={quoteattr(ws_url)}>"
        f"<Parameter name=\"checkin_id\" value={quoteattr(checkin_id)}/>"
        "</Stream></Connect></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/status")
async def twilio_status(checkin_id: str, CallStatus: str = Form(""), CallDuration: str = Form("0")):
    store = get_store()
    checkin = await store.get("checkins", checkin_id)
    log.info("status checkin=%s status=%s", checkin_id, CallStatus)
    if checkin and CallStatus in ("no-answer", "busy", "failed", "canceled"):
        person = await store.get("residents", checkin["resident_id"])
        await rules.on_no_answer(person, checkin_id, checkin.get("attempt", 0))
    return Response(status_code=204)


# ---------------------------------------------------------------- media stream

@app.websocket("/twilio/stream")
async def twilio_stream(ws: WebSocket):
    await ws.accept()
    store = get_store()
    stream_sid = None
    session: SonicSession | None = None
    ctx: CallContext | None = None
    play_until = 0.0  # monotonic time when queued agent audio finishes playing

    async def send_audio(pcm: bytes):
        nonlocal play_until
        if not stream_sid:
            return
        payload = base64.b64encode(pcm16_to_mulaw(pcm)).decode("ascii")
        await ws.send_text(json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}}))
        play_until = max(play_until, time.monotonic()) + len(pcm) / 16000.0  # 8 kHz * 2 bytes

    async def on_interrupt():
        nonlocal play_until
        play_until = time.monotonic()
        if stream_sid:
            await ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))

    async def on_text(role: str, text: str, final: bool):
        if final:
            log.info("[%s] %s", role, text)

    async def hangup():
        # Let the goodbye finish playing, then end the call.
        await asyncio.sleep(max(0.0, play_until - time.monotonic()) + 0.8)
        if ctx and ctx.call_sid:
            await twilio_api.hangup(ctx.call_sid)

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            ev = msg.get("event")
            if ev == "start":
                start = msg["start"]
                stream_sid = start["streamSid"]
                checkin_id = start.get("customParameters", {}).get("checkin_id")
                checkin = await store.get("checkins", checkin_id)
                person = await store.get("residents", checkin["resident_id"])
                await store.update("checkins", checkin_id, {"call_status": "in_progress", "answered_at": now()})
                ctx = CallContext(person=person, checkin_id=checkin_id, call_sid=start.get("callSid", ""),
                                  hangup_cb=hangup)
                memory_bullets = await memory.recall(person)
                call_ctx = {"high_f": 112, "alert_type": "NWS Extreme Heat Warning",
                            "local_time": now().astimezone(PHX).strftime("%I:%M %p").lstrip("0")}
                call_ctx.update(checkin.get("context") or {})
                prompt = build_system_prompt(person, call_ctx, memory_bullets)
                await store.update("checkins", checkin_id, {"memory_used": memory_bullets})
                session = SonicSession(
                    system_prompt=prompt,
                    voice_id=VOICES.get(person.get("language", "en"), "tiffany"),
                    tools=TOOL_SPECS,
                    on_audio=send_audio, on_text=on_text, on_interrupt=on_interrupt,
                    on_tool=lambda name, args: handle_tool(ctx, name, args),
                )
                await session.start()
                await session.send_user_text(opening_nudge(person))
                log.info("stream started checkin=%s person=%s memory=%d", checkin_id, person["_id"], len(memory_bullets))
            elif ev == "media" and session:
                await session.send_audio(mulaw_to_pcm16(base64.b64decode(msg["media"]["payload"])))
            elif ev == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("stream error")
    finally:
        if session:
            await session.close()
        if ctx:
            asyncio.create_task(post_call(ctx, session.transcript if session else []))


async def post_call(ctx: CallContext, transcript: list[dict]) -> None:
    store = get_store()
    ended = now()
    await store.update("checkins", ctx.checkin_id, {
        "call_status": "completed", "ended_at": ended,
        "transcript": transcript,
        "transcript_expires_at": ended + dt.timedelta(days=TRANSCRIPT_TTL_DAYS),
    })
    result = await rules.after_call(ctx.person, ctx.checkin_id, ctx.callback_booked)
    log.info("post-call %s -> %s %s", ctx.checkin_id, result["level"], result["reasons"])
    try:
        from . import notes
        note = await notes.case_note(ctx.person, transcript, result)
        if note:
            await store.update("checkins", ctx.checkin_id, {"case_note": note})
            stamp = ended.astimezone(PHX).strftime("%b %d, %I:%M %p").replace(" 0", " ")
            if note.get("memory_summary"):
                await memory.remember(ctx.person, f"{stamp} check-in: {note['memory_summary']}")
    except Exception:
        log.exception("case note failed")


# ---------------------------------------------------------------- read API (dashboard)

def _jsonable(doc):
    if isinstance(doc, list):
        return [_jsonable(d) for d in doc]
    if isinstance(doc, dict):
        return {k: _jsonable(v) for k, v in doc.items()}
    if isinstance(doc, dt.datetime):
        return doc.isoformat()
    return doc


@app.get("/api/briefing")
async def api_briefing():
    """Gemini-ranked list of who needs a human call, from today's check-ins."""
    from . import notes
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [c for c in await get_store().find("checkins", sort="started_at", limit=500)
            if c.get("started_at") and c["started_at"] >= start]
    if not rows:
        return {"headline": "No check-ins yet today.", "items": [], "calls": 0}
    return JSONResponse(_jsonable(await notes.briefing(rows)))


@app.get("/api/state")
async def api_state():
    store = get_store()
    residents = await store.find("residents")
    checkins = await store.find("checkins", sort="started_at", limit=200)
    alerts = await store.find("alerts", sort="created_at", limit=100)
    resources = await store.find("resources")
    for c in checkins:
        c.pop("transcript", None)
    return JSONResponse(_jsonable({"residents": residents, "checkins": checkins,
                                   "alerts": alerts, "resources": resources}))
