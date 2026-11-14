"""Simulated caller: test a full check-in without a phone.

Gemini plays the person (from a persona), Amazon Polly speaks each reply as 8 kHz
phone audio, and the audio is streamed into the same Nova Sonic session, tools,
rules, memory and Gemini notes a real call uses. Contact alerts run in dry-run
mode and scheduled callbacks are only logged, so no phone rings.

Usage: python scripts/sim_call.py en_warning | es_warning | en_followup | en_clear | crew_ok
"""
import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time

os.environ.setdefault("NOTIFY_DRY_RUN", "1")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import boto3  # noqa: E402

from voice import app as voice_app  # noqa: E402
from voice import memory, notes, scheduler  # noqa: E402
from voice.playbooks import VOICES  # noqa: E402
from voice.prompts import build_system_prompt, opening_nudge  # noqa: E402
from voice.sonic import SonicSession  # noqa: E402
from voice.store import get_store, now  # noqa: E402
from voice.tools import TOOL_SPECS, CallContext, handle_tool  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for noisy in ("httpx", "botocore", "urllib3", "pymongo", "google_genai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("sim")

SCENARIOS = {
    "en_warning": {
        "person": "sim_rosa", "polly_voice": "Joanna", "lang": "en-US",
        "persona": "You are Rosa, 78, at home in Tempe. Your air conditioning stopped working this morning and it is "
                   "very hot inside. You drank a glass of water earlier. You feel a little dizzy, but not confused. "
                   "A ride to a cooling center would help.",
    },
    "en_followup": {
        "person": "sim_rosa", "polly_voice": "Joanna", "lang": "en-US",
        "persona": "You are Rosa, 78. This is a follow-up call. Your AC is still broken. You still feel a little dizzy. "
                   "You have been drinking water.",
    },
    "en_clear": {
        "person": "sim_rosa", "polly_voice": "Joanna", "lang": "en-US",
        "persona": "You are Rosa, 78. Your AC is working fine now, it is cool inside, you are drinking water, "
                   "and you feel fine with no symptoms.",
    },
    "es_warning": {
        "person": "sim_ernesto", "polly_voice": "Miguel", "lang": "es-US",
        "persona": "Eres Ernesto, de 84 años, en Phoenix. Respondes SOLO en español. Tu aire acondicionado funciona "
                   "pero hace calor. No has tomado agua hoy. Tienes un poco de dolor de cabeza. No tienes carro.",
    },
    "crew_ok": {
        "person": "sim_luis", "polly_voice": "Matthew", "lang": "en-US",
        "persona": "You are Luis, a roofer on a crew in Tempe, at work at 1 PM. You drank water in the last hour. "
                   "You have NOT had a shade break since 11. No symptoms. Your coworkers look fine.",
    },
}


def ensure_sim_people():
    """Sim copies of the demo people (no phone numbers, demo=True) so real records stay clean."""
    import copy
    from pymongo import MongoClient
    from voice import config
    db = MongoClient(config.MONGODB_URI, tz_aware=True).heatcheck
    pairs = {"sim_rosa": "res_lopez", "sim_ernesto": "res_garcia", "sim_luis": "wrk_luis"}
    for sim_id, src in pairs.items():
        base = db.residents.find_one({"_id": src})
        doc = copy.deepcopy(base)
        doc.update(_id=sim_id, phone="", demo=True, sim=True, name=base["name"] + " (sim)")
        db.residents.replace_one({"_id": sim_id}, doc, upsert=True)
        for c in db.contacts.find({"resident_id": src}):
            c2 = dict(c, _id=f"{c['_id']}_{sim_id}", resident_id=sim_id)
            db.contacts.replace_one({"_id": c2["_id"]}, c2, upsert=True)


def polly_pcm(text: str, voice: str, lang: str) -> bytes:
    polly = boto3.client("polly", region_name="us-east-2")
    r = polly.synthesize_speech(Text=text, VoiceId=voice, OutputFormat="pcm", SampleRate="8000",
                                LanguageCode=lang, Engine="standard")
    return r["AudioStream"].read()


def caller_reply(persona: str, history: list[str], agent_said: str) -> str:
    from google import genai
    from voice import config
    client = genai.Client(api_key=config.GEMINI_API_KEY, http_options={"timeout": 20000})
    prompt = (f"{persona}\nYou are on a phone call with an automated heat-safety check-in. Reply naturally in ONE short "
              f"spoken sentence, answering only what was just asked. If they say goodbye, say goodbye.\n\n"
              f"Conversation so far:\n" + "\n".join(history[-10:]) + f"\nCaller agent just said: {agent_said}\nYour reply:")
    for model in notes.MODELS:
        try:
            return client.models.generate_content(model=model, contents=prompt).text.strip().strip('"')
        except Exception as e:
            log.warning("caller model %s failed: %s", model, e)
    return "Okay."


async def main(name: str):
    sc = SCENARIOS[name]
    ensure_sim_people()
    store = get_store()
    person = await store.get("residents", sc["person"])

    booked = []

    async def fake_place_call(pid, attempt=0, reason=""):
        booked.append((pid, reason))
        log.info("[sim] callback would be placed for %s (%s)", pid, reason)

    scheduler.place_call = fake_place_call
    scheduler.SECONDS_PER_MINUTE = 3600  # never fire during the sim

    checkin_id = await store.insert("checkins", {
        "resident_id": person["_id"], "resident_name": person["name"], "playbook": person["playbook"],
        "started_at": now(), "attempt": 0, "reason": f"simulated call ({name})", "call_status": "in_progress",
        "demo": True, "sim": True, "context": {"high_f": 112, "alert_type": "NWS Extreme Heat Warning"},
    })
    done = asyncio.Event()

    async def hangup():
        await asyncio.sleep(1.0)
        done.set()

    ctx = CallContext(person=person, checkin_id=checkin_id, hangup_cb=hangup)
    mem = await memory.recall(person)
    prompt = build_system_prompt(person, {"high_f": 112, "alert_type": "NWS Extreme Heat Warning",
                                          "local_time": now().astimezone(voice_app.PHX).strftime("%I:%M %p").lstrip("0")}, mem)
    await store.update("checkins", checkin_id, {"memory_used": mem})

    last_audio = [0.0]
    agent_buf: list[str] = []
    history: list[str] = []
    tool_log: list[str] = []

    async def on_audio(_b):
        last_audio[0] = time.monotonic()

    async def on_text(role, text, final):
        if final and role == "ASSISTANT" and text.strip():
            agent_buf.append(text.strip())

    async def on_tool(n, a):
        tool_log.append(f"{n} {json.dumps(a)}")
        log.info("TOOL %s %s", n, a)
        return await handle_tool(ctx, n, a)

    s = SonicSession(system_prompt=prompt, voice_id=VOICES.get(person.get("language", "en"), "tiffany"),
                     tools=TOOL_SPECS, on_audio=on_audio, on_text=on_text, on_tool=on_tool)
    await s.start()
    await s.send_user_text(opening_nudge(person))

    speaking = asyncio.Lock()
    silence = b"\x00\x00" * 160  # 20 ms at 8 kHz

    async def silence_pump():
        while s.active and not done.is_set():
            if not speaking.locked():
                await s.send_audio(silence)
            await asyncio.sleep(0.02)

    pump = asyncio.create_task(silence_pump())
    t0 = time.monotonic()
    turns = 0
    while not done.is_set() and time.monotonic() - t0 < 180 and turns < 12:
        await asyncio.sleep(0.25)
        quiet = time.monotonic() - last_audio[0]
        if agent_buf and last_audio[0] and quiet > 2.0:
            said = " ".join(agent_buf)
            agent_buf.clear()
            history.append(f"Agent: {said}")
            print(f"\n  AGENT : {said}")
            reply = await asyncio.to_thread(caller_reply, sc["persona"], history, said)
            history.append(f"Caller: {reply}")
            print(f"  CALLER: {reply}")
            pcm = await asyncio.to_thread(polly_pcm, reply, sc["polly_voice"], sc["lang"])
            async with speaking:
                for i in range(0, len(pcm), 320):
                    await s.send_audio(pcm[i:i + 320])
                    await asyncio.sleep(0.02)
            last_audio[0] = time.monotonic()
            turns += 1
    if agent_buf:
        print(f"\n  AGENT : {' '.join(agent_buf)}")
    pump.cancel()
    await s.close()
    print(f"\n  ended_by_agent={ctx.ended}  turns={turns}  secs={time.monotonic() - t0:.0f}")

    await voice_app.post_call(ctx, s.transcript)
    c = await store.get("checkins", checkin_id)
    print("\n=== RESULT ===")
    print("tools      :", *tool_log, sep="\n  ")
    print("rules      :", c.get("risk_level"), c.get("risk_reasons"))
    print("recorded   :", {k: c.get(k) for k in ("ac_working", "water", "rest_break", "symptoms", "coworker_concern")})
    print("case note  :", (c.get("case_note") or {}).get("summary"))
    print("memory used:", mem)
    print("callbacks  :", booked)
    alerts = await store.find("alerts", {"checkin_id": checkin_id})
    print("alerts     :", [(a["level"], a["reason"], a["notified"]) for a in alerts])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "en_warning"))
