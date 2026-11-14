"""Resource Scout: reads cooling-center / library pages with the TinyFish Agent API,
geocodes with Amazon Location Service, and upserts timestamped records into Atlas.

Runs as a Maritime agent (sleeps until a heat warning or a caseworker wakes it),
or locally:  python -m scout.resource_scout [--source NAME]

Every run is logged to the `scout_runs` collection so the dashboard can show the
run log and the "fetched at" time the voice agent quotes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import pathlib
import re
import sys
import time

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from voice import config  # noqa: E402

log = logging.getLogger("scout")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

PHX = dt.timezone(dt.timedelta(hours=-7))
GEO_REGION = os.environ.get("INFRA_REGION", "us-east-2")
TF_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
SOURCES = json.loads((pathlib.Path(__file__).parent / "sources.json").read_text())

SITE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "description": "ok or failed"},
        "reason": {"type": "string"},
        "sites": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "street_address": {"type": "string"},
            "city": {"type": "string"},
            "hours_today": {"type": "string"},
            "open_today": {"type": "boolean"},
            "notes": {"type": "string", "description": "accessibility, pets, water, etc. Empty if none."},
        }, "required": ["name", "street_address", "city", "hours_today", "open_today"]}},
    },
    "required": ["status", "sites"],
}


def goal_for(source: dict, today: dt.datetime) -> str:
    day = today.strftime("%A, %B %d, %Y").replace(" 0", " ")
    return (f"Today is {day}. {source['goal']} For each site return its name, street address, city, and "
            f"TODAY's ({today.strftime('%A')}) opening hours exactly as the site states them. "
            f"Set open_today to false if it is closed today. Include short notes such as wheelchair access "
            f"or pets allowed only if the page states them. Return at most {source.get('max_sites', 12)} sites. "
            f"Set status to 'ok' or 'failed' and explain in reason.")


def run_tinyfish(source: dict, today: dt.datetime, progress) -> dict:
    body = {"url": source["url"], "goal": goal_for(source, today), "output_schema": SITE_SCHEMA,
            "agent_config": {"max_duration_seconds": source.get("max_seconds", 240)}}
    headers = {"X-API-Key": config.TINYFISH_API_KEY, "Content-Type": "application/json"}
    with httpx.stream("POST", TF_URL, json=body, headers=headers, timeout=360) as r:
        if r.status_code >= 300:
            r.read()
            raise RuntimeError(f"TinyFish HTTP {r.status_code}: {r.text[:300]}")
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev.get("type") == "PROGRESS":
                progress(ev.get("purpose", ""))
            elif ev.get("type") == "STREAMING_URL":
                progress("live browser view available", streaming_url=ev.get("streaming_url"))
            elif ev.get("type") == "COMPLETE":
                if ev.get("status") != "COMPLETED":
                    raise RuntimeError(f"TinyFish run {ev.get('status')}: {ev.get('error')}")
                return ev.get("result") or {}
    raise RuntimeError("TinyFish stream ended without COMPLETE")


def normalize_hours(h: str) -> str:
    """'9 a.m. to 5 p.m.' -> '9 AM to 5 PM' so the voice agent reads it cleanly."""
    h = (h or "").strip()
    h = re.sub(r"\b([ap])\.?\s?m\.?", lambda m: m.group(1).upper() + "M", h, flags=re.I)
    h = re.sub(r"\s*[-–]\s*", " to ", h)
    return re.sub(r"\s+", " ", h)


def geocode(client, address: str) -> tuple[float, float] | None:
    try:
        res = client.geocode(QueryText=address, MaxResults=1,
                             Filter={"IncludeCountries": ["USA"]}, BiasPosition=[-112.074, 33.448])
        items = res.get("ResultItems") or []
        if items:
            lng, lat = items[0]["Position"]
            return lng, lat
    except Exception as e:
        log.warning("geocode failed for %s: %s", address, e)
    return None


def site_id(source_name: str, name: str) -> str:
    return "scout_" + hashlib.sha1(f"{source_name}|{name.lower()}".encode()).hexdigest()[:12]


def scout(source_names: list[str] | None = None) -> dict:
    import boto3
    from pymongo import MongoClient

    db = MongoClient(config.MONGODB_URI, tz_aware=True).heatcheck
    geo = boto3.client("geo-places", region_name=GEO_REGION)
    today = dt.datetime.now(PHX)
    sources = [s for s in SOURCES if not source_names or s["name"] in source_names]
    summary = {"sources": [], "upserted": 0}

    for src in sources:
        run_id = db.scout_runs.insert_one({
            "source": src["name"], "url": src["url"], "started_at": dt.datetime.now(dt.timezone.utc),
            "status": "running", "log": [],
        }).inserted_id
        t0 = time.time()

        def progress(msg: str, **extra):
            entry = {"t": round(time.time() - t0, 1), "msg": msg, **extra}
            log.info("[%s] %5.1fs %s", src["name"], entry["t"], msg)
            db.scout_runs.update_one({"_id": run_id}, {"$push": {"log": entry}})

        try:
            progress(f"TinyFish agent reading {src['url']}")
            result = run_tinyfish(src, today, progress)
            sites = result.get("sites") or []
            fetched = dt.datetime.now(dt.timezone.utc)
            n = 0
            for s in sites:
                address = f"{s['street_address']}, {s.get('city') or src.get('default_city', '')}, AZ"
                address = re.sub(r",\s*(\d{5})\s*,", r", \1,", address)
                pos = geocode(geo, address)
                if not pos:
                    continue
                doc = {
                    "type": src.get("resource_type", "cooling_center"),
                    "name": s["name"].strip(), "address": address,
                    "location": {"type": "Point", "coordinates": list(pos)},
                    "hours_today": normalize_hours(s.get("hours_today", "")),
                    "open_today": bool(s.get("open_today")),
                    "notes": (s.get("notes") or "").strip(),
                    "source": src["name"], "source_url": src["url"], "fetched_at": fetched,
                }
                db.resources.replace_one({"_id": site_id(src["name"], s["name"])},
                                         {"_id": site_id(src["name"], s["name"]), **doc}, upsert=True)
                n += 1
            progress(f"Saved {n} of {len(sites)} sites to Atlas")
            db.scout_runs.update_one({"_id": run_id}, {"$set": {
                "status": "ok", "finished_at": dt.datetime.now(dt.timezone.utc),
                "sites_found": len(sites), "sites_saved": n, "reason": result.get("reason")}})
            summary["upserted"] += n
            summary["sources"].append({"source": src["name"], "status": "ok", "saved": n})
        except Exception as e:
            log.exception("source %s failed", src["name"])
            progress(f"Failed: {e}. Keeping last good records.")
            db.scout_runs.update_one({"_id": run_id}, {"$set": {
                "status": "failed", "finished_at": dt.datetime.now(dt.timezone.utc), "error": str(e)}})
            summary["sources"].append({"source": src["name"], "status": "failed", "error": str(e)})
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", help="only run these source names")
    args = ap.parse_args()
    print(json.dumps(scout(args.source), indent=1))
