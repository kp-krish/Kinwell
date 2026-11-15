"""Assemble the final Kinwell demo video from the clips, real call audio and the Nova Sonic voiceover.

Usage: .venv/Scripts/python.exe demo/compose.py   ->  demo/Kinwell_demo.mp4
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
C = "clips"
TMP = ROOT / "_build"
OUT = ROOT / "Kinwell_demo.mp4"

TAKE1 = f"{C}/Kinwell Team - Google Chrome 2026-11-15 00-38-07.mp4"  # permission call screen
TAKE3 = f"{C}/Kinwell Team - Google Chrome 2026-11-15 00-59-19.mp4"  # heat check-in screen
CALL1 = f"{C}/call1_permission.wav"
CALL2 = f"{C}/call2_heat_checkin_take3.wav"
TAKE1_REC0 = 26.2  # seconds into TAKE1 when the Twilio recording of call 1 starts
TAKE3_REC0 = 22.3  # seconds into TAKE3 when the Twilio recording of call 2 starts

BG = "0x14121B"
INK = "0xF4F0FA"
MUTED = "0xA9A1B8"
ICE = "0x8DB4E8"
EMBER = "0xFF8F80"
SERIF_I = "assets/InstrumentSerif-Italic.ttf"
SERIF = "assets/InstrumentSerif-Regular.ttf"
SANS = "assets/segoeui.ttf"
SANS_SB = "assets/seguisb.ttf"
FADE = 0.35

_n = 0


def txt(s: str) -> str:
    """Write text to a file for drawtext (avoids escaping)."""
    global _n
    _n += 1
    p = TMP / f"t{_n}.txt"
    p.write_text(s, encoding="utf-8")
    return p.relative_to(ROOT).as_posix()


def dur(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def draw(text: str, font: str, size: int, color: str, x: str, y: str, start: float = 0, end: float | None = None,
         fade: float = 0.4, box: str | None = None, spacing: int = 10) -> str:
    alpha = f"if(lt(t,{start}),0,if(lt(t,{start + fade}),(t-{start})/{fade},1))"
    if end is not None:
        alpha = f"if(gt(t,{end}),0,if(gt(t,{end - 0.25}),({end}-t)/0.25,{alpha}))"
    s = (f"drawtext=fontfile={font}:textfile={txt(text)}:fontsize={size}:fontcolor={color}:x={x}:y={y}"
         f":line_spacing={spacing}:alpha='{alpha}'")
    if box:
        s += f":box=1:boxcolor={box}:boxborderw=22"
    return s


def label(text: str, d: float) -> str:
    """Small scene label, bottom-left."""
    return draw(text.upper(), SANS_SB, 24, INK, "64", "h-110", start=0.4, end=d - 0.3, box="0x14121B@0.78")


def captions(lines: list[tuple[str, str, float, float]]) -> list[str]:
    out = []
    for who, text, a, b in lines:
        color = ICE if who == "KINWELL" else EMBER
        en = f"enable='between(t,{a},{b})'"
        rows = text.split(chr(10))
        h = 92 + 54 * len(rows)
        y0 = 1080 - 60 - h
        out.append(f"drawbox=x=170:y={y0}:w=1580:h={h}:color=0x14121B@0.97:t=fill:{en}")
        out.append(f"drawbox=x=170:y={y0}:w=1580:h={h}:color=0x3A3548@1:t=2:{en}")
        out.append(f"drawtext=fontfile={SANS_SB}:textfile={txt(who)}:fontsize=24:fontcolor={color}:x=210:y={y0 + 26}:{en}")
        for i, row in enumerate(rows):
            out.append(f"drawtext=fontfile={SANS}:textfile={txt(row)}:fontsize=38:fontcolor={INK}:x=210:"
                       f"y={y0 + 66 + 54 * i}:{en}")
    return out


def run(name: str, inputs: list[str], vchain: str, achain: str, d: float) -> str:
    out = TMP / f"{name}.mp4"
    graph = (vchain + f",fade=t=in:st=0:d={FADE},fade=t=out:st={d - FADE}:d={FADE},format=yuv420p[v];"
             + achain + f",afade=t=in:st=0:d=0.15,afade=t=out:st={d - 0.3}:d=0.3,"
             "aresample=48000,aformat=channel_layouts=stereo[a]")
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for i in inputs:
        args += i.split("\x00") if "\x00" in i else ["-i", i]
    args += ["-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", f"{d:.3f}", "-r", "30",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             out.relative_to(ROOT).as_posix()]
    subprocess.run(args, cwd=ROOT, check=True)
    print(f"  {name}: {d:.1f}s", flush=True)
    return out.name


def vo_mix(vo: list[tuple[str, float]], d: float, base: str = "") -> tuple[list[str], str]:
    """Inputs and an audio chain that places voiceover files at given offsets over silence (or a base chain)."""
    inputs = [f"vo/{k}.wav" for k, _ in vo]
    return inputs, "VO", [(i, off) for i, (_, off) in enumerate(vo)]


# --------------------------------------------------------------------------- scenes

def audio_chain(first_vo_index: int, vo_offsets: list[float], d: float, extra: list[str] | None = None) -> str:
    """Silence bed + delayed voiceovers (+ any extra labeled streams), mixed."""
    parts = [f"anullsrc=r=48000:cl=stereo,atrim=duration={d}[bed]"]
    labels = ["[bed]"]
    for j, off in enumerate(vo_offsets):
        idx = first_vo_index + j
        ms = int(off * 1000)
        parts.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume=1.5[vo{j}]")
        labels.append(f"[vo{j}]")
    labels += extra or []
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first")
    return ";".join(parts)


def scene_desktop(name: str, clip: str, start: float, d: float, vo: list[tuple[str, float]], lab: str,
                  zoom: bool = False, extra_v: list[str] | None = None, speed: float = 1.0) -> str:
    crop = "crop=1520:855:200:0," if zoom else ""
    v = (f"[0:v]trim=start={start}:duration={d * speed},setpts=(PTS-STARTPTS)/{speed},fps=30,{crop}"
         f"scale=1920:1080:flags=lanczos,setsar=1")
    for e in (extra_v or []):
        v += "," + e
    if lab:
        v += "," + label(lab, d)
    a = audio_chain(1, [o for _, o in vo], d)
    return run(name, [clip] + [f"vo/{k}.wav" for k, _ in vo], v, a, d)


def scene_phone(name: str, clip: str, start: float, d: float, speed: float, vo: list[tuple[str, float]],
                eyebrow: str, title: str, sub: str) -> str:
    v = (f"color=c={BG}:s=1920x1080:d={d}:r=30[bg];"
         f"[0:v]trim=start={start}:duration={d * speed},setpts=(PTS-STARTPTS)/{speed},fps=30,"
         f"scale=-2:948:flags=lanczos,pad=iw+12:ih+12:6:6:color=0x2E2A3C[ph];"
         f"[bg][ph]overlay=x=1150:y=(H-h)/2,"
         + draw(eyebrow, SANS_SB, 26, ICE, "150", "330", start=0.3))
    y = 380
    for line in title.split("\n"):
        v += "," + draw(line, SERIF, 96, INK, "146", str(y), start=0.5)
        y += 104
    y += 40
    for line in sub.split("\n"):
        v += "," + draw(line, SANS, 34, MUTED, "150", str(y), start=0.9)
        y += 50
    a = audio_chain(1, [o for _, o in vo], d)
    return run(name, [clip] + [f"vo/{k}.wav" for k, _ in vo], v, a, d)


def scene_card(name: str, d: float, vo: list[tuple[str, float]], draws: list[str], logo: bool = False) -> str:
    v = f"color=c={BG}:s=1920x1080:d={d}:r=30"
    inputs = []
    if logo:
        inputs.append("assets/logo.png")
        v = (f"color=c={BG}:s=1920x1080:d={d}:r=30[bg];[0:v]scale=220:220[lg];"
             f"[bg][lg]overlay=x=(W-w)/2:y=250:enable='gte(t,0.2)'")
    v += "," + ",".join(draws)
    first = len(inputs)
    inputs += [f"vo/{k}.wav" for k, _ in vo]
    a = audio_chain(first, [o for _, o in vo], d)
    return run(name, inputs, v, a, d)


def scene_call(name: str, screen: str, rec0: float, call: str, pieces: list[tuple[float, float]],
               caps: list[tuple[str, str, float, float]], lead_vo: tuple[str, float] | None, lead: float,
               lab: str) -> str:
    """Optional lead-in voiceover over the screen, then the real call audio (cut into pieces) with captions."""
    parts, vlabels, alabels = [], [], []
    t_out = lead
    if lead > 0:
        parts.append(f"[0:v]trim=start={rec0 + pieces[0][0] - lead}:duration={lead},setpts=PTS-STARTPTS,fps=30[vl]")
        vlabels.append("[vl]")
        parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={lead}[al]")
        alabels.append("[al]")
    mapping = []  # (src_start, src_end, out_start)
    for i, (a, b) in enumerate(pieces):
        parts.append(f"[0:v]trim=start={rec0 + a}:end={rec0 + b},setpts=PTS-STARTPTS,fps=30[v{i}]")
        parts.append(f"[1:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1,volume=1.8[a{i}]")
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")
        mapping.append((a, b, t_out))
        t_out += b - a
    d = t_out

    def to_out(t: float) -> float:
        for a, b, o in mapping:
            if a - 0.01 <= t <= b + 0.01:
                return o + (min(max(t, a), b) - a)
        return -1

    out_caps = []
    for who, text, a, b in caps:
        oa, ob = to_out(a), to_out(b)
        if oa >= 0 and ob > oa:
            out_caps.append((who, text, round(oa, 2), round(ob, 2)))
    n = len(vlabels)
    parts.append("".join(vlabels) + f"concat=n={n}:v=1:a=0,crop=1520:855:200:0,scale=1920:1080:flags=lanczos,setsar=1"
                 + "," + draw("LIVE CALL  ·  AMAZON NOVA 2 SONIC", SANS_SB, 26, INK, "(w-text_w)/2", "190",
                              start=lead + 0.2, box="0xB4532A@0.95")
                 + "," + ",".join(captions(out_caps)))
    vchain = ";".join(parts)
    achain_parts = ["".join(alabels) + f"concat=n={n}:v=0:a=1[call]"]
    inputs = [screen, call]
    if lead_vo:
        inputs.append(f"vo/{lead_vo[0]}.wav")
        ms = int(lead_vo[1] * 1000)
        achain_parts.append(f"[2:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume=1.5,"
                            f"apad=whole_dur={d}[lv]")
        achain_parts.append("[call][lv]amix=inputs=2:normalize=0:duration=first")
    else:
        achain_parts.append("[call]anull")
    return run(name, inputs, vchain, ";".join(achain_parts), d)


# --------------------------------------------------------------------------- the film

def main() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir()
    for f in ("segoeui.ttf", "seguisb.ttf"):
        if not (ROOT / "assets" / f).exists():
            shutil.copy(f"C:/Windows/Fonts/{f}", ROOT / "assets" / f)
    v = {p.stem: dur(f"vo/{p.name}") for p in (ROOT / "vo").glob("v*.wav")}
    print("voiceover:", {k: round(x, 1) for k, x in sorted(v.items())})
    segs = []

    # 1. Hook
    d = v["v01"] + 2.2
    segs.append(scene_desktop(
        "s01_hook", f"{C}/dash_overview.mp4", 0, d, [("v01", 1.0)], "",
        extra_v=["eq=brightness=-0.18:saturation=0.8", "boxblur=10:2",
                 draw("Every summer, people die alone at home in the heat.", SERIF_I, 78, INK,
                      "(w-text_w)/2", "(h-text_h)/2-40", start=0.6),
                 draw("Every winter, in the cold.", SERIF_I, 78, MUTED, "(w-text_w)/2", "(h-text_h)/2+60",
                      start=2.6)]))

    # 2. Family adds a parent (assistant, sped up)
    d = v["v02"] + 3.2
    segs.append(scene_phone(
        "s02_assistant", f"{C}/family_assistant_phone.mp4", 2, d, (56 / d), [("v02", 0.6)],
        "FAMILY SITE", "Add a parent\nin about a minute", "A Gemini assistant asks one thing at a time:\nnumber, "
        "address, language, backup contact.\nTyped or spoken."))

    # 3. Permission call (real audio)
    segs.append(scene_call(
        "s03_permission", TAKE1, TAKE1_REC0, CALL1, [(0.0, 23.2), (25.2, 28.85)],
        [("KINWELL", "Hello John, this is an automated call from Kinwell.\nKrish, a family member, signed you up.", 0.3, 5.5),
         ("KINWELL", "On days with dangerous heat or cold, Kinwell calls to ask a few quick questions,\n"
                     "like whether your heat or air conditioning is working and how you feel.", 6.1, 13.9),
         ("KINWELL", "If something sounds wrong, we let Krish know.\nIs it okay if we call you on those days?", 14.5, 20.8),
         ("JOHN", "Yes.", 21.3, 23.2),
         ("KINWELL", "Thank you, John. I will call back if needed. Goodbye, John.", 25.3, 28.85)],
        ("v03", 0.3), v["v03"] + 0.8, "Permission first"))

    # 4. Warning hits
    d = v["v04"] + 0.9
    segs.append(scene_desktop("s04_warning", TAKE3, 12.0, d, [("v04", 0.3)], "NWS extreme heat warning", zoom=True))

    # 5. The check-in call (real audio), tool-lookup pauses cut
    segs.append(scene_call(
        "s05_checkin", TAKE3, TAKE3_REC0, CALL2, [(8.6, 27.2), (29.5, 47.6), (49.6, 53.2)],
        [("KINWELL", "Hi, it's Kinwell checking on you.\nIs your air conditioning working right now?", 9.0, 12.4),
         ("JOHN", "Yes, it's working.", 12.5, 14.9),
         ("KINWELL", "How hot does it feel inside your home?", 15.0, 16.7),
         ("JOHN", "I think it's about ninety-five degrees.", 16.7, 19.8),
         ("KINWELL", "Have you been drinking water today?", 19.8, 21.6),
         ("JOHN", "Yes.", 21.7, 23.4),
         ("KINWELL", "Are you feeling any dizziness, headache,\nnausea, or confusion?", 23.4, 25.1),
         ("JOHN", "I feel a little dizzy.", 25.1, 27.2),
         ("KINWELL", "The nearest cooling center is Tempe Public Library,\nabout 3 miles away.", 29.5, 33.6),
         ("KINWELL", "It is closed right now and opens at 9 AM today.", 33.6, 37.9),
         ("KINWELL", "Until then, try staying in the coolest room, taking a cool shower,\nor visiting a friend's place.", 38.3, 43.6),
         ("KINWELL", "Would a ride there help?", 44.1, 46.2),
         ("JOHN", "Yes.", 46.3, 47.6),
         ("KINWELL", "I'll call back soon to check on you. Goodbye, John.", 49.6, 53.2)],
        None, 0, "Real call · heat check-in"))

    # 5b. Result lands on the board
    d = v["v05"] + 2.0
    segs.append(scene_desktop("s05b_result", TAKE3, TAKE3_REC0 + 56.0, d, [("v05", 0.5)],
                              "Warning: 95°F inside + dizziness", zoom=True))

    # 6. Family hears right away
    d = v["v06"] + 2.2
    segs.append(scene_phone(
        "s06_family", f"{C}/family_home_phone.mp4", 7.0, d, 1.0, [("v06", 0.4)],
        "FAMILY ALERT", "Family hears\nright away", "A phone call to the first contact,\nthen the next one if "
        "nobody answers.\nThe family site shows what happened."))

    # 7. Team view
    d = v["v07"] + 2.6
    segs.append(scene_desktop("s07a_board", f"{C}/dash_overview.mp4", 1.0, d, [("v07", 0.4)],
                              "Team dashboard · Gemini ranks who to call first", speed=1.6))
    d = v["v08"] + 1.4
    segs.append(scene_desktop("s07b_detail", f"{C}/dash_call_detail.mp4", 2.0, d, [("v08", 0.4)],
                              "Case note · who's been told · transcript · Supermemory", speed=1.3))
    d = v["v09"] + 1.6
    segs.append(scene_desktop("s07c_map", f"{C}/dash_map.mp4", 2.0, d, [("v09", 0.4)],
                              "Cooling centers · TinyFish web agent · MongoDB Atlas geo"))
    d = v["v10"] + 2.2
    segs.append(scene_phone(
        "s07d_oncall", f"{C}/dash_phone.mp4", 0.5, d, 1.6, [("v10", 0.4)],
        "ON CALL", "The same board\nin your pocket", "Needs you, map and everyone,\nupdated live."))

    # 8. Cold
    d = v["v11"] + 1.6
    segs.append(scene_desktop("s08_cold", f"{C}/family_home_desktop.mp4", 3.0, d, [("v11", 0.4)],
                              "Cold mode · heat, power and carbon-monoxide questions"))

    # 9. Built with
    d = v["v12"] + 2.4
    rows = ["Amazon Nova 2 Sonic  ·  Amazon Bedrock  ·  Step Functions  ·  ECS Fargate",
            "Amazon Cognito  ·  Amazon Location  ·  Amplify  ·  EventBridge",
            "MongoDB Atlas  ·  Supermemory  ·  Gemini  ·  TinyFish on Maritime",
            "National Weather Service API  ·  Twilio"]
    draws = [draw("BUILT WITH", SANS_SB, 28, ICE, "(w-text_w)/2", "300", start=0.2)]
    for i, r in enumerate(rows):
        draws.append(draw(r, SANS, 44, INK if i < 3 else MUTED, "(w-text_w)/2", str(390 + i * 90), start=0.4 + i * 0.35))
    segs.append(scene_card("s09_built", d, [("v12", 0.5)], draws))

    # 10. Close
    d = v["v13"] + 3.2
    segs.append(scene_card("s10_close", d, [("v13", 0.6)], [
        draw("Kinwell", SERIF_I, 120, INK, "(w-text_w)/2", "500", start=0.3),
        draw("Know they're okay on the hottest and coldest days.", SANS, 40, MUTED, "(w-text_w)/2", "660", start=0.9),
    ], logo=True))

    lst = TMP / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "_build/list.txt",
                    "-c", "copy", "_build/joined.mp4"], cwd=ROOT, check=True)
    # Soft ambient pad under everything, ducked whenever someone speaks; then loudness-normalize.
    mix = ("[1:a]volume=0.16,afade=t=in:d=2,aformat=channel_layouts=stereo[pad];[0:a]asplit[m][sc];"
           "[pad][sc]sidechaincompress=threshold=0.015:ratio=8:attack=40:release=700[duck];"
           "[m][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "_build/joined.mp4", "-i", "assets/pad.wav",
                    "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", OUT.name], cwd=ROOT, check=True)
    print(f"done: {OUT}  ({dur(OUT.name):.1f}s)")


if __name__ == "__main__":
    main()
