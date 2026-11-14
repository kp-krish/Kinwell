"""Smoke test: open a Nova Sonic stream, send a text turn plus silence,
confirm we get audio and a transcript back. Writes reply audio to a WAV file.

Usage: python scripts/sonic_smoke.py [out.wav]
"""
import asyncio
import logging
import pathlib
import sys
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from voice.sonic import OUTPUT_SAMPLE_RATE, SonicSession  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


async def main(out_path: str) -> None:
    audio = bytearray()
    texts = []

    async def on_audio(b: bytes):
        audio.extend(b)

    async def on_text(role, text, final):
        if final:
            texts.append(f"{role}: {text}")

    s = SonicSession(
        system_prompt="You are a friendly automated heat-safety caller. Keep replies to one short sentence.",
        on_audio=on_audio,
        on_text=on_text,
    )
    await s.start()
    await s.send_user_text("Hi, please greet me in one sentence.")
    # Stream ~6 s of silence in 20 ms frames so the session behaves like a live call.
    frame = b"\x00\x00" * (s and int(8000 * 0.02))
    for _ in range(300):
        await s.send_audio(frame)
        await asyncio.sleep(0.02)
    await s.close()

    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(OUTPUT_SAMPLE_RATE)
        w.writeframes(bytes(audio))
    print("TRANSCRIPT:", *texts, sep="\n  ")
    print(f"AUDIO: {len(audio)} bytes ({len(audio) / 2 / OUTPUT_SAMPLE_RATE:.1f}s) -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "sonic_smoke.wav"))
