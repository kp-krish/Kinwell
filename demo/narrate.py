"""Generate the demo voiceover with Amazon Nova 2 Sonic (voice "matthew"), one WAV per line.

Usage: .venv/Scripts/python.exe demo/narrate.py   ->  demo/vo/<id>.wav (24 kHz mono)
"""
import asyncio
import os
import pathlib
import sys
import time
import wave

os.environ["SONIC_OUTPUT_RATE"] = "24000"
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from voice.sonic import SonicSession  # noqa: E402

OUT = ROOT / "vo"
LINES = {
    "v01": "Every summer, older adults die alone at home in the heat. Most of them had someone who would have come, "
           "if only they had known in time.",
    "v02": "Kinwell starts with family. Maria tells the assistant she wants to add her dad. It asks for one thing at a "
           "time: his number, his address, the language he speaks, and a backup contact.",
    "v03": "Before any check-ins, Kinwell calls and asks for permission. Nothing starts until he says yes.",
    "v04": "When the National Weather Service issues an extreme heat or cold warning where someone lives, Kinwell "
           "starts calling. This is a real call.",
    "v05": "Ninety-five degrees inside counts as a warning, even with the A C on. The agent runs on Amazon Nova 2 Sonic, "
           "speech to speech, in real time.",
    "v06": "Seconds later, the family gets a phone alert, and the family site shows exactly what happened.",
    "v07": "Caseworkers see everyone on one board: who needs a human, what Kinwell is already handling, and who is "
           "safe. Gemini ranks who to call first.",
    "v08": "Every call becomes a case note, with the answers, who has been told, and the full transcript. Supermemory "
           "lets the next call pick up where the last one left off.",
    "v09": "Cooling and warming centers come from a TinyFish web agent that checks city websites for today's hours, "
           "stored in MongoDB Atlas with geospatial search.",
    "v10": "And whoever is on call gets the same board on their phone.",
    "v11": "Kinwell works in the cold too. Is the heat on? Is there power and gas? Is anyone using an oven or a "
           "generator to stay warm?",
    "v12": "Built on A W S, MongoDB Atlas, Supermemory, Gemini, and TinyFish.",
    "v13": "Kinwell. Know they're okay, on the hottest and coldest days.",
}
SYSTEM = ("You are the voiceover narrator for a short product film. Each user message is a script line. "
          "Read the line aloud exactly as written, word for word, in a calm, warm, unhurried documentary voice. "
          "Do not add, drop, or change any words. Say nothing else: no greeting, no reply, no comment.")


async def narrate(key: str, text: str, voice: str = "matthew") -> tuple[float, str]:
    audio = bytearray()
    said: list[str] = []
    last = [time.monotonic()]

    async def on_audio(pcm: bytes):
        audio.extend(pcm)
        last[0] = time.monotonic()

    async def on_text(role, t, final):
        if role == "ASSISTANT" and t.strip():
            said.append(("F:" if final else "S:") + t.strip())

    s = SonicSession(system_prompt=SYSTEM, voice_id=voice, on_audio=on_audio, on_text=on_text, temperature=0.3)
    await s.start()

    async def silence():
        while s.active:
            await s.send_audio(b"\x00" * 1600)
            await asyncio.sleep(0.1)

    asyncio.create_task(silence())
    await s.send_user_text(f'Script line: "{text}"')
    start = time.monotonic()
    while time.monotonic() - start < 60:
        await asyncio.sleep(0.25)
        if audio and time.monotonic() - last[0] > 2.5:
            break
    await s.close()
    path = OUT / f"{key}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(bytes(audio))
    return len(audio) / 48000, " ".join(said)


async def main(keys: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    for k in keys or list(LINES):
        dur, said = await narrate(k, LINES[k])
        print(f"{k} {dur:5.1f}s | {said}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
