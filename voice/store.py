"""Data access. MongoDB Atlas when MONGODB_URI is set, otherwise an in-memory
store seeded with demo data so the voice loop can be developed before Atlas exists.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
import math
import uuid

from . import config
from .seed import seed_documents

UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


def _haversine_m(lng1, lat1, lng2, lat2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class MemoryStore:
    def __init__(self) -> None:
        self.db = {k: {d["_id"]: d for d in v} for k, v in seed_documents().items()}
        for k in ("checkins", "alerts"):
            self.db.setdefault(k, {})

    async def get(self, coll: str, _id: str) -> dict | None:
        d = self.db.get(coll, {}).get(_id)
        return copy.deepcopy(d) if d else None

    async def find(self, coll: str, flt: dict | None = None, sort: str | None = None,
                   desc: bool = True, limit: int = 0) -> list[dict]:
        flt = flt or {}
        out = [copy.deepcopy(d) for d in self.db.get(coll, {}).values()
               if all(d.get(k) == v for k, v in flt.items())]
        if sort:
            out.sort(key=lambda d: d.get(sort) or dt.datetime.min.replace(tzinfo=UTC), reverse=desc)
        return out[:limit] if limit else out

    async def insert(self, coll: str, doc: dict) -> str:
        doc.setdefault("_id", uuid.uuid4().hex)
        self.db.setdefault(coll, {})[doc["_id"]] = copy.deepcopy(doc)
        return doc["_id"]

    async def update(self, coll: str, _id: str, fields: dict) -> None:
        if _id in self.db.get(coll, {}):
            self.db[coll][_id].update(copy.deepcopy(fields))

    async def upsert(self, coll: str, _id: str, fields: dict) -> None:
        self.db.setdefault(coll, {}).setdefault(_id, {"_id": _id}).update(copy.deepcopy(fields))

    async def nearest_resource(self, lng: float, lat: float, rtype: str, max_m: float = 15000) -> dict | None:
        best, best_d = None, max_m
        for r in self.db.get("resources", {}).values():
            if r.get("type") != rtype or not r.get("open_today", True):
                continue
            rl, ra = r["location"]["coordinates"]
            d = _haversine_m(lng, lat, rl, ra)
            if d <= best_d:
                best, best_d = r, d
        if not best:
            return None
        out = copy.deepcopy(best)
        out["distance_m"] = best_d
        return out


class MongoStore:
    def __init__(self, uri: str) -> None:
        from pymongo import MongoClient
        self.client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=8000)
        self.mdb = self.client.heatcheck

    async def _run(self, fn, *a, **kw):
        return await asyncio.to_thread(fn, *a, **kw)

    async def get(self, coll, _id):
        return await self._run(self.mdb[coll].find_one, {"_id": _id})

    async def find(self, coll, flt=None, sort=None, desc=True, limit=0):
        def q():
            cur = self.mdb[coll].find(flt or {})
            if sort:
                cur = cur.sort(sort, -1 if desc else 1)
            if limit:
                cur = cur.limit(limit)
            return list(cur)
        return await self._run(q)

    async def insert(self, coll, doc):
        doc.setdefault("_id", uuid.uuid4().hex)
        await self._run(self.mdb[coll].insert_one, doc)
        return doc["_id"]

    async def update(self, coll, _id, fields):
        await self._run(self.mdb[coll].update_one, {"_id": _id}, {"$set": fields})

    async def upsert(self, coll, _id, fields):
        """Insert or update in one atomic write (safe when two requests race to fill a cache)."""
        await self._run(self.mdb[coll].update_one, {"_id": _id}, {"$set": fields}, upsert=True)

    async def nearest_resource(self, lng, lat, rtype, max_m=15000):
        """Nearest open resource via $geoNear on the 2dsphere index.
        Prefers live Resource Scout records; falls back to seed records."""
        def q(extra):
            pipeline = [
                {"$geoNear": {
                    "near": {"type": "Point", "coordinates": [lng, lat]},
                    "distanceField": "distance_m", "maxDistance": max_m, "spherical": True,
                    "query": {"type": rtype, "open_today": True, **extra}}},
                {"$limit": 1},
            ]
            res = list(self.mdb.resources.aggregate(pipeline))
            return res[0] if res else None
        live = await self._run(q, {"source_url": {"$ne": "seed"}})
        return live or await self._run(q, {})


_store = None


def get_store():
    global _store
    if _store is None:
        _store = MongoStore(config.MONGODB_URI) if config.MONGODB_URI else MemoryStore()
    return _store


async def calls_today(person_id: str) -> int:
    """Calls placed today (Phoenix calendar day; Arizona has no DST) for the daily cap."""
    phx = dt.timezone(dt.timedelta(hours=-7))
    start = now().astimezone(phx).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await get_store().find("checkins", {"resident_id": person_id})
    return sum(1 for r in rows if r.get("started_at") and r["started_at"] >= start)
