"""Address geocoding (Amazon Location Service, US Census fallback) and phone normalization."""
from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

from .store import get_store, now

log = logging.getLogger("geo")
GEO_REGION = os.environ.get("INFRA_REGION", "us-east-2")


def normalize_phone(raw: str | None) -> str | None:
    """US numbers to E.164 (+1XXXXXXXXXX). Returns None if it is not a plausible US number."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return None
    return "+1" + digits


def _key(address: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", address.lower()).strip()


def _amazon(address: str) -> dict | None:
    import boto3
    client = boto3.client("geo-places", region_name=GEO_REGION)
    res = client.geocode(QueryText=address, MaxResults=1, Filter={"IncludeCountries": ["USA"]})
    items = res.get("ResultItems") or []
    if not items:
        return None
    it = items[0]
    lng, lat = it["Position"]
    a = it.get("Address") or {}
    return {"lat": lat, "lng": lng, "label": a.get("Label") or address,
            "city": a.get("Locality"), "state": (a.get("Region") or {}).get("Code"),
            "zip": a.get("PostalCode"), "source": "amazon-location"}


async def _census(address: str) -> dict | None:
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, params={"address": address, "benchmark": "Public_AR_Current", "format": "json"})
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches") or []
    if not matches:
        return None
    m = matches[0]
    comp = m.get("addressComponents") or {}
    return {"lat": m["coordinates"]["y"], "lng": m["coordinates"]["x"], "label": m.get("matchedAddress", address),
            "city": (comp.get("city") or "").title() or None, "state": comp.get("state"), "zip": comp.get("zip"),
            "source": "us-census"}


async def geocode(address: str) -> dict | None:
    address = (address or "").strip()
    if len(address) < 5:
        return None
    store = get_store()
    key = _key(address)
    hit = await store.get("geocode_cache", key)
    if hit:
        return hit["result"]
    result = None
    try:
        result = await asyncio.to_thread(_amazon, address)
    except Exception as e:
        log.warning("Amazon Location geocode failed (%s); trying Census", e)
    if not result:
        try:
            result = await _census(address)
        except Exception as e:
            log.warning("Census geocode failed: %s", e)
    if result:
        try:
            await store.upsert("geocode_cache", key, {"result": result, "at": now()})
        except Exception as e:
            log.warning("geocode cache write failed: %s", e)
    return result
