"""Record demo screen clips of the Kinwell team dashboard and family site with Playwright.

Usage:  .venv/Scripts/python.exe demo/record_clips.py [scene ...]
Clips land in demo/clips/<scene>.webm (+ .mp4). Needs FAMILY_DEMO_EMAIL / FAMILY_DEMO_PASSWORD in .env.
Nothing here places a phone call: Simulate / Check-now buttons are never pressed.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import shutil
import subprocess
import sys
import time

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "clips"
DASH = "https://main.d2glxv1ik89dxx.amplifyapp.com"
FAMILY = "https://main.d6r9gfc2uhb84.amplifyapp.com"
DESKTOP = {"width": 1440, "height": 810}  # recorded 1:1, upscaled to 1920x1080 by ffmpeg
PHONE = {"width": 390, "height": 844}

load_dotenv(ROOT.parent / ".env")
READY: dict[str, float] = {}


def ready() -> None:
    """Scenes call this once the page shows real content; everything before it is trimmed."""
    READY.setdefault("at", time.monotonic())


async def glide(page: Page, selector: str, steps: int = 25) -> None:
    """Move the mouse smoothly onto an element (so the viewer can follow it) and hover."""
    box = await page.locator(selector).first.bounding_box()
    if box:
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)


async def click(page: Page, selector: str, pause: float = 0.6) -> None:
    await glide(page, selector)
    await asyncio.sleep(pause)
    await page.locator(selector).first.click()


async def scroll(page: Page, total: int, step: int = 6, delay: float = 0.03, el: str | None = None) -> None:
    for _ in range(0, abs(total), step):
        if el:
            await page.locator(el).first.evaluate(f"(n) => n.scrollBy(0, {step if total > 0 else -step})")
        else:
            await page.mouse.wheel(0, step if total > 0 else -step)
        await asyncio.sleep(delay)


# ------------------------------------------------------------------ team dashboard

async def dash_overview(page: Page) -> None:
    await page.goto(DASH + "/")
    await page.wait_for_selector("text=Open call", timeout=20000)
    ready()
    await asyncio.sleep(3)
    await scroll(page, 520)
    await asyncio.sleep(2)
    await scroll(page, -520)
    await asyncio.sleep(1)
    await click(page, "button:has-text('Rank now')")
    await page.wait_for_selector("ol li", timeout=30000)
    await asyncio.sleep(5)


async def dash_call_detail(page: Page) -> None:
    await page.goto(DASH + "/")
    await page.wait_for_selector("text=Open call", timeout=20000)
    ready()
    await asyncio.sleep(1.5)
    card = page.locator("article", has_text="John").first
    if not await card.count():
        card = page.locator("article").first
    await card.scroll_into_view_if_needed()
    btn = card.locator("button:has-text('Open call')")
    box = await btn.bounding_box()
    await page.mouse.move(box["x"] + 30, box["y"] + 15, steps=25)
    await asyncio.sleep(0.6)
    await btn.click()
    await page.wait_for_selector("[role=dialog]")
    await asyncio.sleep(3)
    await scroll(page, 1400, step=5, delay=0.035, el="[role=dialog]")
    await asyncio.sleep(2.5)


async def dash_map(page: Page) -> None:
    await page.goto(DASH + "/#map")
    await page.wait_for_selector(".center-marker", timeout=20000)
    await asyncio.sleep(3)  # tiles
    ready()
    centers = page.locator(".center-marker")
    n = await centers.count()
    for i in (n // 3, n // 2, (2 * n) // 3):
        box = await centers.nth(i).bounding_box()
        if box:
            await page.mouse.move(box["x"] + 7, box["y"] + 7, steps=30)
            await asyncio.sleep(3)
    await page.mouse.move(960, 560, steps=20)
    for _ in range(6):
        await page.mouse.wheel(0, -120)
        await asyncio.sleep(0.35)
    await asyncio.sleep(3)


async def dash_tabs(page: Page) -> None:
    await page.goto(DASH + "/")
    await page.wait_for_selector("text=Open call", timeout=20000)
    ready()
    await asyncio.sleep(1.5)
    for tab in ("People", "Crews", "Cooling & warming"):
        await click(page, f"nav button:has-text('{tab}')")
        await asyncio.sleep(3)
        await scroll(page, 300)
        await asyncio.sleep(1)
    await click(page, "nav button:has-text('Right now')")
    await asyncio.sleep(2)


async def dash_phone(page: Page) -> None:
    await page.goto(DASH + "/")
    await page.wait_for_selector("text=Open call", timeout=20000)
    ready()
    await asyncio.sleep(3)
    await scroll(page, 700, step=5)
    await asyncio.sleep(1.5)
    await page.locator("nav[aria-label=Main] button:has-text('Map')").last.click()
    await asyncio.sleep(5)
    await page.locator("nav[aria-label=Main] button:has-text('Everyone')").last.click()
    await asyncio.sleep(3)
    await page.locator("nav[aria-label=Main] button:has-text('Needs you')").last.click()
    await asyncio.sleep(2)


# ------------------------------------------------------------------ family site

async def family_sign_in(page: Page, show: bool = True) -> None:
    await page.goto(FAMILY + "/")
    await page.wait_for_selector("input[type=email]", timeout=20000)
    await asyncio.sleep(0.8)
    if show:
        ready()
        await asyncio.sleep(2.5)
    await page.locator("input[type=email]").type(os.environ["FAMILY_DEMO_EMAIL"], delay=45 if show else 0)
    await page.locator("input[type=password]").type(os.environ["FAMILY_DEMO_PASSWORD"], delay=45 if show else 0)
    if show:
        await asyncio.sleep(0.6)
    await page.locator("form button.btn-ink").first.click()
    await page.wait_for_selector("text=Rosa", timeout=20000)


async def family_home(page: Page) -> None:
    await family_sign_in(page)
    await asyncio.sleep(3.5)
    await page.locator("text=Rosa").first.click()
    await asyncio.sleep(3)
    await scroll(page, 700, step=5)
    await asyncio.sleep(1)
    radio = page.locator("[role=radio]:has-text('Cold')")
    if await radio.count():
        await radio.first.click()
        await asyncio.sleep(1.2)
        await page.locator("[role=radio]:has-text('Heat')").first.click()
    await asyncio.sleep(2.5)


ASSISTANT_SCRIPT = [
    "I want to add my dad",
    "His name is Miguel",
    "602-555-0147",
    "1820 E Thomas Rd, Phoenix AZ 85016",
    "He speaks Spanish",
    "He's 81, has diabetes and lives alone",
    "My neighbor Ana, 602-555-0182",
]


async def family_assistant(page: Page) -> None:
    await family_sign_in(page, show=False)
    await asyncio.sleep(1.5)
    ready()
    add = page.locator("button:has-text('Add someone'):visible, button:has-text('Add'):visible").first
    await add.click()
    box = page.locator("#chat")
    await box.wait_for(timeout=15000)
    await asyncio.sleep(2.5)
    for line in ASSISTANT_SCRIPT:
        await box.click()
        await box.type(line, delay=55)
        await asyncio.sleep(0.4)
        await page.keyboard.press("Enter")
        # the message must actually send (input clears); the app ignores Enter while it is busy
        for _ in range(20):
            if not await box.input_value():
                break
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
        # wait for the reply to start typing, then to finish
        try:
            await page.wait_for_selector(".caret", timeout=40000)
        except Exception:
            pass
        await page.wait_for_function("() => !document.querySelector('.caret')", timeout=60000)
        await asyncio.sleep(2.2)
    await asyncio.sleep(4)  # summary + "Add and ask" button visible; it is never pressed


SCENES = {
    # name: (fn, viewport, scale)
    "dash_overview": (dash_overview, DESKTOP, (1920, 1080)),
    "dash_call_detail": (dash_call_detail, DESKTOP, (1920, 1080)),
    "dash_map": (dash_map, DESKTOP, (1920, 1080)),
    "dash_tabs": (dash_tabs, DESKTOP, (1920, 1080)),
    "dash_phone": (dash_phone, PHONE, (780, 1688)),
    "family_home_phone": (family_home, PHONE, (780, 1688)),
    "family_assistant_phone": (family_assistant, PHONE, (780, 1688)),
    "family_home_desktop": (family_home, DESKTOP, (1920, 1080)),
    "family_assistant_desktop": (family_assistant, DESKTOP, (1920, 1080)),
}


async def record(name: str) -> pathlib.Path:
    fn, vp, out_size = SCENES[name]
    tmp = OUT / f"_tmp_{name}"
    shutil.rmtree(tmp, ignore_errors=True)
    READY.clear()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = await browser.new_context(viewport=vp, device_scale_factor=1, record_video_dir=str(tmp),
                                        record_video_size=vp, is_mobile=vp["width"] < 600, color_scheme="light")
        t0 = time.monotonic()
        page = await ctx.new_page()
        try:
            await fn(page)
        finally:
            video = page.video
            await ctx.close()
            await browser.close()
        src = pathlib.Path(await video.path())
    dest = OUT / f"{name}.webm"
    shutil.move(src, dest)
    shutil.rmtree(tmp, ignore_errors=True)
    trim = max(0.0, READY.get("at", t0) - t0 + 0.3)
    mp4 = dest.with_suffix(".mp4")
    w, h = out_size
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{trim:.2f}", "-i", str(dest),
                    "-vf", f"scale={w}:{h}:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "16", "-preset", "slow", "-r", "30", str(mp4)], check=True)
    return mp4


async def main(names: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    for n in names or list(SCENES):
        try:
            print("recorded", await record(n))
        except Exception as e:
            print("FAILED", n, type(e).__name__, str(e)[:300])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
