"""Kinwell voice server: Twilio Media Streams <-> Amazon Nova 2 Sonic.

Run locally:  python -m uvicorn voice.app:app --port 8080
Twilio needs a public wss URL, so set PUBLIC_HOST (e.g. a cloudflared tunnel host).
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import re
import logging
import time
from xml.sax.saxutils import quoteattr

from fastapi import FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from . import config, family, memory, rules, scheduler, twilio_api, weather
from .audio import mulaw_to_pcm16, pcm16_to_mulaw
from .playbooks import VOICES
from .prompts import build_system_prompt, opening_nudge
from .sonic import SonicSession
from .store import calls_today, get_store, now
from .tools import CallContext, handle_tool, tools_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="Kinwell voice")

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(family.router)

TRANSCRIPT_TTL_DAYS = 30
PHX = dt.timezone(dt.timedelta(hours=-7))  # Arizona has no DST


def local_now(person: dict) -> dt.datetime:
    from zoneinfo import ZoneInfo
    try:
        return now().astimezone(ZoneInfo(person.get("tz") or "America/Phoenix"))
    except Exception:
        return now().astimezone(PHX)


def public_base(request: Request | None = None) -> str:
    host = config.PUBLIC_HOST or (request.headers.get("host") if request else "")
    return host.replace("https://", "").replace("http://", "").rstrip("/")


# ---------------------------------------------------------------- placing calls

async def place_call(person_id: str, attempt: int = 0, reason: str = "scheduled check-in",
                     context: dict | None = None, task_token: str | None = None,
                     purpose: str = "checkin") -> dict:
    store = get_store()
    person = await store.get("residents", person_id)
    if not person:
        raise HTTPException(404, f"unknown person {person_id}")
    if not person.get("phone"):
        raise HTTPException(400, f"{person_id} has no phone number")
    if purpose == "checkin" and (person.get("paused") or person.get("status") not in (None, "active")):
        # No check-ins before consent, after a "no", or while the family has paused calls.
        log.info("skip call to %s: status=%s paused=%s", person_id, person.get("status"), person.get("paused"))
        if task_token:
            from . import escalation
            await escalation.report_followup(task_token, "no_answer", ["calls paused or not consented"])
        return {"skipped": "not active"}
    # Never ring someone who is already on (or being dialed for) a check-in call.
    recent = now() - dt.timedelta(minutes=10)
    active = [c for c in await store.find("checkins", {"resident_id": person_id}, sort="started_at", limit=5)
              if c.get("call_status") in ("dialing", "in_progress") and c.get("started_at") and c["started_at"] >= recent]
    if active:
        if task_token:
            # A ladder follow-up while a call is live: that call's result answers the ladder.
            await store.update("checkins", active[0]["_id"], {"task_token": task_token})
            log.info("follow-up attached to active call %s for %s", active[0]["_id"], person_id)
            return {"attached": active[0]["_id"]}
        log.info("skip call to %s: call already in progress", person_id)
        return {"skipped": "call already in progress"}
    if await calls_today(person_id) >= config.DAILY_CALL_CAP:
        log.warning("daily call cap reached for %s", person_id)
        return {"skipped": "daily call cap reached"}
    scheduler.cancel(person_id)  # this call replaces any pending retry/callback

    checkin_id = await store.insert("checkins", {
        "resident_id": person_id, "resident_name": person.get("name"),
        "playbook": person.get("playbook"), "started_at": now(), "attempt": attempt,
        "reason": reason, "call_status": "dialing", "context": context or {}, "purpose": purpose,
        **({"task_token": task_token} if task_token else {}),
    })
    base = public_base()
    res = await twilio_api.create_call(
        person["phone"],
        url=f"https://{base}/twilio/voice?checkin_id={checkin_id}",
        status_callback=f"https://{base}/twilio/status?checkin_id={checkin_id}",
        detect_machine=True,
        amd_callback=f"https://{base}/twilio/amd?checkin_id={checkin_id}",
    )
    await store.update("checkins", checkin_id, {"call_sid": res.get("sid")})
    log.info("dialing %s checkin=%s sid=%s", person_id, checkin_id, res.get("sid"))
    return {"checkin_id": checkin_id, "call_sid": res.get("sid")}


scheduler.place_call = place_call
family.place_call = place_call


import hmac  # noqa: E402
import os  # noqa: E402

from fastapi import Header  # noqa: E402


def _require(token_env: str, supplied: str | None) -> None:
    """Shared-secret check. Unset token = local dev, allowed."""
    expected = os.environ.get(token_env, "")
    if expected and not (supplied and hmac.compare_digest(supplied, expected)):
        raise HTTPException(401, "unauthorized")


def require_dashboard(x_api_key: str | None = Header(None)) -> None:
    _require("DASHBOARD_KEY", x_api_key)


def require_internal(x_internal_token: str | None = Header(None)) -> None:
    _require("INTERNAL_TOKEN", x_internal_token)


@app.post("/internal/notify")
async def internal_notify(payload: dict, x_internal_token: str | None = Header(None)):
    """Step Functions rung: alert one contact on the ladder."""
    require_internal(x_internal_token)
    store = get_store()
    person = await store.get("residents", payload["person_id"])
    step = int(payload.get("step", 0))
    ladder = await rules.contacts_for(person)
    reason = "; ".join(payload.get("reasons") or []) or payload.get("level", "warning")
    if payload.get("level") == "no_answer" and step > 0:
        reason = "still not reachable after follow-up"
    notified = await rules.escalate_now(person, payload.get("checkin_id"), reason, emergency=False,
                                        findings=payload.get("findings", "") if step == 0 else "",
                                        rung=step)
    return {"notified": notified, "rung": step, "has_next_rung": step + 1 < len(ladder),
            "next_contact": (ladder[step + 1]["name"] if step + 1 < len(ladder) else None)}


@app.post("/internal/followup")
async def internal_followup(payload: dict, x_internal_token: str | None = Header(None)):
    """Step Functions rung: place a follow-up call; its result is sent back with the task token."""
    require_internal(x_internal_token)
    orig = await get_store().get("checkins", payload.get("checkin_id") or "") or {}
    ctx = orig.get("context") or {"hazard": "heat", "high_f": 112, "alert_type": "NWS Extreme Heat Warning"}
    try:
        res = await place_call(payload["person_id"], attempt=0, reason="escalation follow-up",
                               context=ctx, task_token=payload["task_token"])
    except HTTPException as e:
        res = {"skipped": e.detail}
    if res.get("skipped"):
        from . import escalation
        await escalation.report_followup(payload["task_token"], "no_answer", [str(res["skipped"])])
    return res


@app.post("/internal/heat-run")
async def internal_heat_run(payload: dict, x_internal_token: str | None = Header(None)):
    """Risk engine: a real NWS heat alert starts a heat-day run."""
    require_internal(x_internal_token)
    store = get_store()
    alert_id = payload.get("alert_id") or "nws"
    if await store.get("heat_runs", alert_id):
        return {"skipped": "already ran for this alert"}
    await store.insert("heat_runs", {"_id": alert_id, "alert_type": payload.get("alert_type"),
                                     "headline": payload.get("headline"), "started_at": now()})
    return await api_simulate({**payload, "source": "nws"})


@app.post("/internal/weather-poll")
async def internal_weather_poll(x_internal_token: str | None = Header(None)):
    """Risk engine (every 30 min): NWS heat and cold alerts for every zone where enrolled people live."""
    require_internal(x_internal_token)
    return await weather.poll(place_call)


@app.get("/health")
async def health():
    return {"ok": True, "store": type(get_store()).__name__}


@app.post("/calls")
async def start_call(payload: dict, x_api_key: str | None = Header(None)):
    """Start a check-in call: {"person_id": "res_lopez", "high_f": 112, "alert_type": "NWS Extreme Heat Warning"}"""
    require_dashboard(x_api_key)
    ctx = {k: payload[k] for k in ("high_f", "alert_type") if k in payload}
    return await place_call(payload["person_id"], reason=payload.get("reason", "manual"), context=ctx)


# ---------------------------------------------------------------- Twilio webhooks

@app.post("/twilio/voice")
async def twilio_voice(request: Request, checkin_id: str, AnsweredBy: str = Form("")):
    if AnsweredBy.startswith("machine") or AnsweredBy == "fax":
        # Voicemail is not a check-in: hang up and treat it as no answer (retry, then escalate).
        store = get_store()
        checkin = await store.get("checkins", checkin_id)
        log.info("voicemail detected checkin=%s answered_by=%s", checkin_id, AnsweredBy)
        if checkin:
            await store.update("checkins", checkin_id, {"answered_by": AnsweredBy})
            person = await store.get("residents", checkin["resident_id"])
            asyncio.create_task(rules.on_no_answer(person, checkin_id, checkin.get("attempt", 0),
                                                   why="reached voicemail"))
        return Response(content="<Response><Hangup/></Response>", media_type="application/xml")
    ws_url = f"wss://{public_base(request)}/twilio/stream"
    twiml = (
        "<Response><Connect>"
        f"<Stream url={quoteattr(ws_url)}>"
        f"<Parameter name=\"checkin_id\" value={quoteattr(checkin_id)}/>"
        "</Stream></Connect></Response>"
    )
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/amd")
async def twilio_amd(checkin_id: str, AnsweredBy: str = Form(""), CallSid: str = Form("")):
    """Async answering-machine verdict. A person is already talking to the agent; on voicemail, hang up."""
    log.info("amd checkin=%s answered_by=%s", checkin_id, AnsweredBy)
    if AnsweredBy.startswith("machine") or AnsweredBy == "fax":
        store = get_store()
        checkin = await store.get("checkins", checkin_id)
        if checkin and not checkin.get("answered_by"):
            await store.update("checkins", checkin_id, {"answered_by": AnsweredBy})
            if CallSid:
                try:
                    await twilio_api.hangup(CallSid)
                except Exception:
                    log.exception("hangup after voicemail failed")
            person = await store.get("residents", checkin["resident_id"])
            asyncio.create_task(rules.on_no_answer(person, checkin_id, checkin.get("attempt", 0),
                                                   why="reached voicemail"))
    return Response(status_code=204)


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
    t_start: float | None = None  # when Twilio's stream started, for first-audio latency

    async def send_audio(pcm: bytes):
        nonlocal play_until, t_start
        if not stream_sid:
            return
        if t_start is not None:
            log.info("first agent audio %.2fs after stream start", time.monotonic() - t_start)
            t_start = None
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
        # Safety net: the model sometimes says goodbye but never calls end_call, leaving dead air.
        if final and role == "ASSISTANT" and ctx and not ctx.ended and GOODBYE_RE.search(text):
            if await ready_to_end(ctx):
                ctx.ended = True
                log.info("goodbye heard without end_call; hanging up checkin=%s", ctx.checkin_id)
                asyncio.create_task(fallback_hangup())

    async def fallback_hangup():
        await asyncio.sleep(1.5)  # audio for the goodbye can still be arriving after its text
        await hangup()

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
                t_start = time.monotonic()
                start = msg["start"]
                stream_sid = start["streamSid"]
                checkin_id = start.get("customParameters", {}).get("checkin_id")
                checkin = await store.get("checkins", checkin_id)
                person = await store.get("residents", checkin["resident_id"])
                await store.update("checkins", checkin_id, {"call_status": "in_progress", "answered_at": now()})
                purpose = checkin.get("purpose", "checkin")
                call_ctx = {"hazard": "heat", "high_f": 112, "alert_type": "NWS Extreme Heat Warning"}
                call_ctx.update(checkin.get("context") or {})
                call_ctx["purpose"] = purpose
                call_ctx["local_time"] = local_now(person).strftime("%I:%M %p").lstrip("0")
                hazard = call_ctx.get("hazard", "heat")
                ctx = CallContext(person=person, checkin_id=checkin_id, call_sid=start.get("callSid", ""),
                                  hangup_cb=hangup, hazard=hazard, purpose=purpose)
                memory_bullets = await memory.recall(person) if purpose == "checkin" else []
                prompt = build_system_prompt(person, call_ctx, memory_bullets)
                await store.update("checkins", checkin_id, {"memory_used": memory_bullets})
                session = SonicSession(
                    system_prompt=prompt,
                    voice_id=VOICES.get(person.get("language", "en"), "tiffany"),
                    tools=tools_for(purpose, hazard),
                    on_audio=send_audio, on_text=on_text, on_interrupt=on_interrupt,
                    on_tool=lambda name, args: handle_tool(ctx, name, args),
                )
                t0 = time.monotonic()
                await session.start()
                await session.send_user_text(opening_nudge(person))
                log.info("sonic ready in %.2fs checkin=%s", time.monotonic() - t0, checkin_id)
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


GOODBYE_RE = re.compile(r"\b(good ?bye|bye now|adi[oó]s|hasta luego)\b", re.I)


async def ready_to_end(ctx: CallContext) -> bool:
    """The call has what it needs: consent answered, or the check-in recorded, or an emergency flagged."""
    if any(f.get("level") == "emergency" for f in ctx.flags):
        return True
    checkin = await get_store().get("checkins", ctx.checkin_id) or {}
    return "consent" in checkin if ctx.purpose == "consent" else "symptoms" in checkin


async def post_call(ctx: CallContext, transcript: list[dict]) -> None:
    store = get_store()
    ended = now()
    if ((await store.get("checkins", ctx.checkin_id)) or {}).get("answered_by", "").startswith(("machine", "fax")):
        await store.update("checkins", ctx.checkin_id, {"call_status": "no_answer", "ended_at": ended})
        log.info("post-call %s: voicemail, handled as no answer", ctx.checkin_id)
        return
    await store.update("checkins", ctx.checkin_id, {
        "call_status": "completed", "ended_at": ended,
        "transcript": transcript,
        "transcript_expires_at": ended + dt.timedelta(days=TRANSCRIPT_TTL_DAYS),
    })
    result = await rules.after_call(ctx.person, ctx.checkin_id, ctx.callback_booked)
    log.info("post-call %s -> %s %s", ctx.checkin_id, result["level"], result["reasons"])
    if ctx.purpose == "consent":
        return
    try:
        from . import notes
        note = await notes.case_note(ctx.person, transcript, result)
        if note:
            await store.update("checkins", ctx.checkin_id, {"case_note": note})
            stamp = ended.astimezone(local_now(ctx.person).tzinfo).strftime("%b %d, %I:%M %p").replace(" 0", " ")
            if note.get("memory_summary"):
                kind = "cold-weather" if ctx.hazard == "cold" else "heat"
                await memory.remember(ctx.person, f"{stamp} {kind} check-in: {note['memory_summary']}")
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
    if type(doc).__name__ == "ObjectId":
        return str(doc)
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
    checkins = await store.find("checkins", sort="started_at", limit=300)
    alerts = await store.find("alerts", sort="created_at", limit=100)
    resources = await store.find("resources")
    crews = await store.find("crews")
    runs = await store.find("scout_runs", sort="started_at", limit=5)
    weather_alerts = await store.find("weather_alerts", {"active": True})
    # Simulator test people (scripts/sim_call.py) stay out of the dashboard.
    sim_ids = {r["_id"] for r in residents if r.get("sim") or r.get("status") == "removed"}
    residents = [r for r in residents if r["_id"] not in sim_ids]
    checkins = [c for c in checkins if c.get("resident_id") not in sim_ids]
    alerts = [a for a in alerts if a.get("resident_id") not in sim_ids]
    for c in checkins:
        c.pop("transcript", None)
    return JSONResponse(_jsonable({"residents": residents, "checkins": checkins, "alerts": alerts,
                                   "resources": resources, "crews": crews, "scout_runs": runs,
                                   "weather_alerts": weather_alerts, "server_time": now()}))


@app.get("/api/checkins/{checkin_id}")
async def api_checkin(checkin_id: str):
    c = await get_store().get("checkins", checkin_id)
    if not c:
        raise HTTPException(404)
    return JSONResponse(_jsonable(c))


@app.post("/api/alerts/{alert_id}/ack")
async def api_ack(alert_id: str, payload: dict | None = None, x_api_key: str | None = Header(None)):
    require_dashboard(x_api_key)
    who = (payload or {}).get("by", "caseworker")
    await get_store().update("alerts", alert_id, {"acknowledged_by": who, "resolved_at": now()})
    return {"ok": True}


@app.post("/api/simulate-heat-warning")
async def simulate_route(payload: dict | None = None, x_api_key: str | None = Header(None)):
    require_dashboard(x_api_key)
    return await api_simulate({**(payload or {}), "hazard": "heat"})


@app.post("/api/simulate-weather")
async def simulate_weather_route(payload: dict | None = None, x_api_key: str | None = Header(None)):
    """Demo trigger for either hazard: {"hazard": "cold"} simulates an NWS Extreme Cold Warning."""
    require_dashboard(x_api_key)
    return await api_simulate(payload)


async def api_simulate(payload: dict | None = None):
    """Demo trigger: an NWS heat (or cold) warning starts a check-in run.
    Calls every eligible enrolled person with a phone number (or just person_id), and wakes Resource Scout."""
    payload = payload or {}
    hazard = payload.get("hazard", "heat") if payload.get("hazard") in ("heat", "cold") else "heat"
    if hazard == "cold":
        ctx = {"hazard": "cold", "low_f": payload.get("low_f", -4), "alert_type": "NWS Extreme Cold Warning"}
    else:
        ctx = {"hazard": "heat", "high_f": payload.get("high_f", 112), "alert_type": "NWS Extreme Heat Warning"}
    store = get_store()
    targets = [payload["person_id"]] if payload.get("person_id") else \
        [r["_id"] for r in await store.find("residents") if weather.eligible(r, hazard)]
    placed = []
    for pid in targets:
        try:
            placed.append({pid: await place_call(pid, reason=f"NWS {hazard} warning", context=ctx)})
        except HTTPException as e:
            placed.append({pid: {"error": e.detail}})
    scout = await wake_scout() if payload.get("wake_scout", True) else None
    return {"calls": placed, "scout": scout}


@app.post("/api/crews/{crew_id}/start-shift")
async def api_start_shift(crew_id: str, x_api_key: str | None = Header(None)):
    """Crew Check: call every opted-in worker on this crew now; later check-ins follow the crew interval."""
    require_dashboard(x_api_key)
    store = get_store()
    workers = [r for r in await store.find("residents", {"crew_id": crew_id}) if r.get("phone") and not r.get("demo")]
    out = []
    for w in workers:
        try:
            out.append({w["_id"]: await place_call(w["_id"], reason="crew shift check-in",
                                                   context={"high_f": 112, "alert_type": "NWS Extreme Heat Warning"})})
        except HTTPException as e:
            out.append({w["_id"]: {"error": e.detail}})
    return {"calls": out}


@app.post("/api/scout/refresh")
async def api_scout_refresh(x_api_key: str | None = Header(None)):
    require_dashboard(x_api_key)
    return await wake_scout(trigger="caseworker")


async def wake_scout(trigger: str = "heat_warning") -> dict:
    """Wake the Resource Scout agent on Maritime and start a run. It sleeps again when idle."""
    import os
    import pathlib
    import httpx
    key = os.environ.get("MARITIME_API_KEY") or os.environ.get("MARITIME_API")
    state_file = pathlib.Path(__file__).resolve().parent.parent / "scout" / "maritime_agent.json"
    agent_id = os.environ.get("MARITIME_AGENT_ID") or (
        json.loads(state_file.read_text())["agent_id"] if state_file.exists() else None)
    if not key or not agent_id:
        return {"status": "skipped", "reason": "Maritime agent not deployed"}
    base = "https://api.maritime.sh"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            await c.post(f"{base}/api/agents/{agent_id}/start", headers={"Authorization": f"Bearer {key}"})
            for _ in range(30):
                try:
                    r = await c.get(f"{base}/a/{agent_id}/health")
                    if r.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2)
            r = await c.post(f"{base}/a/{agent_id}/run", json={"trigger": trigger},
                             headers={"Authorization": f"Bearer {os.environ.get('SCOUT_TOKEN', '')}"})
            return {"status": "woken", "run": r.json() if r.content else r.status_code}
    except Exception as e:
        log.exception("wake scout failed")
        return {"status": "error", "error": str(e)}
