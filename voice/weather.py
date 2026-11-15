"""National Weather Service: zones, forecasts and active heat/cold alerts for every place
someone enrolled lives. Works anywhere in the US, not just Maricopa County.

The scheduled risk engine calls /internal/weather-poll; poll() looks up active alerts for
all zones with enrolled people and starts check-in calls for the matching hazard.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx

from .playbooks import COLD_EVENTS, HEAT_EVENTS, WATCH_EVENTS, hazard_of
from .store import get_store, now

log = logging.getLogger("weather")

API = "https://api.weather.gov"
HEADERS = {"User-Agent": "Kinwell weather-safety prototype", "Accept": "application/geo+json"}
FORECAST_TTL = dt.timedelta(minutes=60)
RECALL_GAP = dt.timedelta(hours=12)  # one hazard check-in per person per 12 hours, even if NWS reissues


async def _get(url: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _last(url: str | None) -> str:
    return (url or "").rstrip("/").rsplit("/", 1)[-1]


async def point_info(lat: float, lng: float) -> dict | None:
    """NWS zones, time zone and forecast URL for a US location. None outside NWS coverage."""
    try:
        p = (await _get(f"{API}/points/{lat:.4f},{lng:.4f}"))["properties"]
    except Exception as e:
        log.warning("NWS points lookup failed for %s,%s: %s", lat, lng, e)
        return None
    rel = (p.get("relativeLocation") or {}).get("properties") or {}
    zones = [z for z in (_last(p.get("forecastZone")), _last(p.get("county")), _last(p.get("fireWeatherZone"))) if z]
    return {"nws_zones": list(dict.fromkeys(zones)), "tz": p.get("timeZone") or "America/Phoenix",
            "forecast_url": p.get("forecast"), "city": rel.get("city"), "state": rel.get("state")}


async def ensure_zones(person: dict) -> dict:
    """Backfill NWS zones for people enrolled before national coverage existed."""
    if person.get("nws_zones") or not person.get("location"):
        return person
    lng, lat = person["location"]["coordinates"]
    info = await point_info(lat, lng)
    if info:
        await get_store().update("residents", person["_id"], info)
        person = {**person, **info}
    return person


def _alert_row(f: dict) -> dict | None:
    p = f.get("properties") or {}
    hazard = hazard_of(p.get("event", ""))
    if not hazard:
        return None
    return {
        "_id": p.get("id") or f.get("id"), "event": p.get("event"), "hazard": hazard,
        "headline": p.get("headline"), "severity": p.get("severity"),
        "zones": list(dict.fromkeys(((p.get("geocode") or {}).get("UGC") or [])
                                    + [_last(z) for z in p.get("affectedZones") or []])),
        "onset": p.get("onset"), "ends": p.get("ends") or p.get("expires"),
        "calls": p.get("event") in HEAT_EVENTS or p.get("event") in COLD_EVENTS,
        "watch": p.get("event") in WATCH_EVENTS,
    }


async def active_alerts(zones: list[str]) -> list[dict]:
    out: dict[str, dict] = {}
    zones = sorted(set(zones))
    for i in range(0, len(zones), 25):
        try:
            data = await _get(f"{API}/alerts/active", {"zone": ",".join(zones[i:i + 25])})
        except Exception as e:
            log.warning("NWS alerts failed for %s: %s", zones[i:i + 25], e)
            continue
        for f in data.get("features", []):
            row = _alert_row(f)
            if row:
                out[row["_id"]] = row
    return list(out.values())


async def forecast(person: dict) -> dict:
    """Today's high and tonight's low (F), cached per forecast URL for an hour."""
    url = person.get("forecast_url")
    if not url:
        return {}
    store = get_store()
    hit = await store.get("weather_cache", url)
    if hit and hit.get("fetched_at") and now() - hit["fetched_at"] < FORECAST_TTL:
        return hit["data"]
    try:
        periods = (await _get(url))["properties"]["periods"]
    except Exception as e:
        log.warning("forecast failed: %s", e)
        return (hit or {}).get("data", {})
    day = next((p for p in periods if p.get("isDaytime")), None)
    night = next((p for p in periods if not p.get("isDaytime")), None)
    data = {"high_f": day and day.get("temperature"), "low_f": night and night.get("temperature"),
            "now_label": periods[0].get("name"), "now_f": periods[0].get("temperature"),
            "short": periods[0].get("shortForecast")}
    try:
        await store.upsert("weather_cache", url, {"data": data, "fetched_at": now()})
    except Exception as e:  # a cache write must never break a request
        log.warning("forecast cache write failed: %s", e)
    return data


async def alert_for(person: dict) -> dict | None:
    """Most relevant cached active alert for this person's zones (warnings before watches)."""
    zones = set(person.get("nws_zones") or [])
    if not zones:
        return None
    rows = await get_store().find("weather_alerts", {"active": True})
    mine = [a for a in rows if zones & set(a.get("zones") or [])]
    mine.sort(key=lambda a: (not a.get("calls"), a.get("hazard") != "heat"))
    return mine[0] if mine else None


def eligible(person: dict, hazard: str | None = None) -> bool:
    """May get a check-in call: consented (or seeded), not paused, has a phone, right hazard."""
    if person.get("playbook") != "resident" or not person.get("phone") or person.get("paused"):
        return False
    if person.get("status") not in (None, "active"):
        return False
    return hazard is None or hazard in (person.get("hazards") or ["heat"])


def call_context(alert: dict | None, hazard: str, fc: dict) -> dict:
    ctx = {"hazard": hazard,
           "alert_type": "NWS " + (alert or {}).get("event", "Extreme Heat Warning" if hazard == "heat"
                                                    else "Extreme Cold Warning")}
    if hazard == "cold":
        ctx["low_f"] = fc.get("low_f") if fc.get("low_f") is not None else "unknown"
    else:
        ctx["high_f"] = fc.get("high_f") if fc.get("high_f") is not None else "unknown"
    return ctx


async def recently_called(person_id: str, hazard: str) -> bool:
    rows = await get_store().find("checkins", {"resident_id": person_id}, sort="started_at", limit=10)
    cutoff = now() - RECALL_GAP
    return any(((r.get("context") or {}).get("hazard", "heat") == hazard and r.get("purpose", "checkin") == "checkin"
                and r.get("started_at") and r["started_at"] >= cutoff) for r in rows)


async def poll(place_call) -> dict:
    """Find active NWS heat/cold alerts for every enrolled person's zones and start calls."""
    store = get_store()
    people = [await ensure_zones(p) for p in await store.find("residents")
              if p.get("playbook") == "resident" and not p.get("sim") and not p.get("demo")]
    zones = sorted({z for p in people for z in p.get("nws_zones") or []})
    alerts = await active_alerts(zones) if zones else []

    # Cache: mark everything inactive, then upsert what is active now.
    for old in await store.find("weather_alerts", {"active": True}):
        if old["_id"] not in {a["_id"] for a in alerts}:
            await store.update("weather_alerts", old["_id"], {"active": False})
    for a in alerts:
        if not await store.get("weather_alerts", a["_id"]):
            a = {**a, "first_seen": now()}
        await store.upsert("weather_alerts", a["_id"], {**a, "active": True, "seen_at": now()})

    placed = []
    for a in alerts:
        if not a["calls"]:
            continue
        for p in people:
            if not (set(p.get("nws_zones") or []) & set(a["zones"])) or not eligible(p, a["hazard"]):
                continue
            if await recently_called(p["_id"], a["hazard"]):
                continue
            ctx = call_context(a, a["hazard"], await forecast(p))
            try:
                res = await place_call(p["_id"], reason=f"NWS {a['event']}", context=ctx)
            except Exception as e:
                res = {"error": str(e)}
            placed.append({"person": p["_id"], "alert": a["event"], "result": res})
    log.info("weather poll: %d zones, %d alerts, %d calls", len(zones), len(alerts), len(placed))
    return {"zones": len(zones), "alerts": [{"event": a["event"], "zones": a["zones"][:5]} for a in alerts],
            "calls": placed}
