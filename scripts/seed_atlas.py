"""Create Atlas indexes and upsert demo seed data.

Usage: python scripts/seed_atlas.py [--reset-activity]
  --reset-activity  also clears checkins and alerts (fresh demo state)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pymongo import ASCENDING, DESCENDING, GEOSPHERE, MongoClient  # noqa: E402

from voice import config  # noqa: E402
from voice.seed import seed_documents  # noqa: E402


def main() -> None:
    if not config.MONGODB_URI:
        sys.exit("MONGODB_URI is not set in .env")
    db = MongoClient(config.MONGODB_URI, tz_aware=True, serverSelectionTimeoutMS=10000).heatcheck
    db.command("ping")
    print("connected to Atlas")

    db.resources.create_index([("location", GEOSPHERE)])
    db.residents.create_index([("location", GEOSPHERE)])
    db.checkins.create_index("transcript_expires_at", expireAfterSeconds=0)  # TTL
    db.checkins.create_index([("resident_id", ASCENDING), ("started_at", DESCENDING)])
    db.alerts.create_index([("created_at", DESCENDING)])
    db.contacts.create_index([("resident_id", ASCENDING), ("escalation_order", ASCENDING)])
    print("indexes ok")

    for coll, docs in seed_documents().items():
        for d in docs:
            db[coll].replace_one({"_id": d["_id"]}, d, upsert=True)
        print(f"{coll}: {len(docs)} upserted")

    if "--reset-activity" in sys.argv:
        print("checkins cleared:", db.checkins.delete_many({}).deleted_count)
        print("alerts cleared:", db.alerts.delete_many({}).deleted_count)


if __name__ == "__main__":
    main()
