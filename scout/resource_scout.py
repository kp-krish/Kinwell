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
try:  # local dev: reuse the repo .env; on Maritime, env vars are injected
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _env(*names: str) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return ""


def _mongo_uri() -> str:
    from urllib.parse import quote_plus
    uri = _env("MONGODB_URI")
    user, pw = _env("MONGODB_USER"), _env("MONGODB_PASSWORD")
    if user:
        uri = uri.replace("<db_username>", quote_plus(user))
    if pw:
        uri = uri.replace("<db_password>", quote_plus(pw))
    return uri


TINYFISH_API_KEY = _env("TINYFISH_API_KEY", "TINYFISH_API", "TINY_FISH_API")
MONGODB_URI = _mongo_uri()

log = logging.getLogger("scout")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

PHX = dt.timezone(dt.timedelta(hours=-7))
GEO_REGION = os.environ.get("INFRA_REGION", "us-east-2")
TF_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
SOURCES = json.loads((pathlib.Path(__file__).parent / "sources.json").read_text())

SITE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "reason": {"type": "string"},
        "sites": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "street_address": {"type": "string"},
            "city": {"type": "string"},
            "hours_today": {"type": "string"},
            "open_today": {"type": "boolean"},
            "notes": {"type": "string"},
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
    headers = {"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"}
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


def _addr_key(address: str) -> str:
    """Street + city, ignoring punctuation, state and ZIP, so format changes still hit the cache."""
    words = re.sub(r"[^a-z0-9]+", " ", address.lower()).split()
    words = [w for w in words if w not in ("az", "arizona", "usa") and not re.fullmatch(r"\d{5}", w)]
    return " ".join(dict.fromkeys(words))


def geocode(db, client, address: str) -> tuple[float, float] | None:
    """Atlas geocache first (addresses rarely move); Amazon Location only when
    AWS credentials are present. Without them, the record is saved as pending
    and the AWS side backfills it."""
    key = _addr_key(address)
    hit = db.geocache.find_one({"_id": key})
    if hit:
        return tuple(hit["coordinates"])
    if client is None:
        return None
    try:
        res = client.geocode(QueryText=address, MaxResults=1,
                             Filter={"IncludeCountries": ["USA"]}, BiasPosition=[-112.074, 33.448])
        items = res.get("ResultItems") or []
        if items:
            lng, lat = items[0]["Position"]
            db.geocache.replace_one({"_id": key}, {"_id": key, "address": address, "coordinates": [lng, lat]},
                                    upsert=True)
            return lng, lat
    except Exception as e:
        log.warning("geocode failed for %s: %s", address, e)
    return None


def _geo_client():
    try:
        import boto3
        session = boto3.Session()
        if session.get_credentials() is None:
            return None
        return session.client("geo-places", region_name=GEO_REGION)
    except Exception:
        return None


def site_id(source_name: str, name: str) -> str:
    return "scout_" + hashlib.sha1(f"{source_name}|{name.lower()}".encode()).hexdigest()[:12]


def scout(source_names: list[str] | None = None) -> dict:
    from pymongo import MongoClient

    db = MongoClient(MONGODB_URI, tz_aware=True).heatcheck
    geo = _geo_client()
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
                street = s["street_address"].strip().rstrip(".")
                city = (s.get("city") or src.get("default_city", "")).strip()
                if re.search(r"\bAZ\b", street):
                    address = street
                else:
                    zipm = re.search(r",?\s*(\d{5})$", street)
                    street = street[:zipm.start()] if zipm else street
                    address = f"{street}, {city}, AZ" + (f" {zipm.group(1)}" if zipm else "")
                pos = geocode(db, geo, address)
                doc = {
                    "type": src.get("resource_type", "cooling_center"),
                    "name": s["name"].strip(), "address": address,
                    "hours_today": normalize_hours(s.get("hours_today", "")),
                    "open_today": bool(s.get("open_today")),
                    "notes": (s.get("notes") or "").strip(),
                    "source": src["name"], "source_url": src["url"], "fetched_at": fetched,
                }
                if pos:
                    doc["location"] = {"type": "Point", "coordinates": list(pos)}
                else:
                    doc["pending_geocode"] = True
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
