"""Twilio <-> Nova Sonic audio conversion.

Twilio Media Streams: 8 kHz, 8-bit mu-law, base64.
Nova Sonic (configured here): 8 kHz, 16-bit signed little-endian PCM.
Same sample rate, so only the codec changes.
"""
import audioop  # provided by audioop-lts on Python 3.13+


def mulaw_to_pcm16(data: bytes) -> bytes:
    return audioop.ulaw2lin(data, 2)


def pcm16_to_mulaw(data: bytes) -> bytes:
    return audioop.lin2ulaw(data, 2)
