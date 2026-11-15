"""Add a synthetic, clearly-labeled demo population so the dashboard and briefing
look like a real heat-day run. Every record has demo=True and no phone number,
so nothing here can ever be called.

Usage: python scripts/demo_population.py [--remove]
"""
import datetime as dt
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pymongo import MongoClient  # noqa: E402

from voice import config  # noqa: E402

FIRST = ["Alma", "Bernard", "Carmen", "Dolores", "Eugene", "Fatima", "Gloria", "Harold", "Irene", "Jorge",
         "Kathleen", "Leonard", "Marisol", "Norma", "Oscar", "Patricia", "Ramon", "Shirley", "Teodoro", "Vera",
         "Walter", "Yolanda", "Arturo", "Beatriz", "Clarence", "Delia", "Esperanza", "Frank", "Guadalupe",
         "Herbert", "Ines", "Joaquin", "Lorraine", "Manuel", "Nadine", "Ofelia", "Raymond"]
LAST = ["Alvarez", "Begay", "Castillo", "Duran", "Ellis", "Flores", "Gutierrez", "Hughes", "Ibarra", "Jensen",
        "Kim", "Lucero", "Montoya", "Nguyen", "Ortega", "Patel", "Quintana", "Reyes", "Sandoval", "Tso",
        "Urias", "Valdez", "Walker", "Yazzie", "Zamora"]
AREAS = [  # (lat, lng, zip, city) spread across the Valley
    (33.4484, -112.0740, "85004", "Phoenix"), (33.5092, -112.1124, "85015", "Phoenix"),
    (33.4152, -112.1210, "85041", "Phoenix"), (33.5722, -112.0891, "85023", "Phoenix"),
    (33.4255, -111.9400, "85281", "Tempe"), (33.4152, -111.8315, "85201", "Mesa"),
    (33.3062, -111.8413, "85225", "Chandler"), (33.5387, -112.1860, "85301", "Glendale"),
    (33.4936, -112.0080, "85016", "Phoenix"), (33.3528, -111.7890, "85233", "Gilbert"),
    (33.4942, -111.9261, "85251", "Scottsdale"), (33.4373, -112.3496, "85338", "Goodyear"),
]
RISKS = [["age 81", "lives alone"], ["age 74", "diabetes"], ["age 88", "dementia", "lives alone"],
         ["age 69", "heart condition"], ["age 77", "no car"], ["age 92", "uses oxygen"], ["age 71", "lives alone"]]

# A handful need a human; the rest checked in fine.
OUTCOMES = (["clear"] * 31) + ["warning_ac", "warning_dizzy", "warning_water", "no_answer", "no_answer", "warning_ac"]


def main():
    db = MongoClient(config.MONGODB_URI, tz_aware=True).heatcheck
    db.residents.delete_many({"demo": True})
    db.checkins.delete_many({"demo": True})
    db.alerts.delete_many({"demo": True})
    if "--remove" in sys.argv:
        print("demo population removed")
        return

    rnd = random.Random(42)
    now = dt.datetime.now(dt.timezone.utc)
    rnd.shuffle(OUTCOMES)
    for i, outcome in enumerate(OUTCOMES):
        lat, lng, zp, city = AREAS[i % len(AREAS)]
        lat += rnd.uniform(-0.03, 0.03)
        lng += rnd.uniform(-0.035, 0.035)
        first, last = FIRST[i % len(FIRST)], LAST[(i * 7) % len(LAST)]
        rid = f"demo_{i:02d}"
        db.residents.insert_one({
            "_id": rid, "name": f"{first} {last}", "first_name": first, "phone": "", "demo": True,
            "language": rnd.choice(["en", "en", "es"]), "address": f"{city}, AZ {zp}", "zip": zp,
            "location": {"type": "Point", "coordinates": [lng, lat]},
            "risk_factors": rnd.choice(RISKS), "playbook": "resident", "caseworker_id": "cw_1",
        })
        started = now - dt.timedelta(minutes=rnd.randint(3, 55))
        c = {"_id": f"demo_ck_{i:02d}", "resident_id": rid, "resident_name": f"{first} {last}", "demo": True,
             "playbook": "resident", "started_at": started, "ended_at": started + dt.timedelta(minutes=2),
             "attempt": 0, "reason": "NWS Extreme Heat Warning", "transcript": [], "purpose": "checkin",
             "context": {"hazard": "heat", "high_f": 112, "alert_type": "NWS Extreme Heat Warning"},
             "transcript_expires_at": now + dt.timedelta(days=30)}
        if outcome == "clear":
            c.update(call_status="completed", risk_level="clear", risk_reasons=[], ac_working="yes", water="yes",
                     symptoms=[], case_note={"summary": f"{first}'s AC is working and {first} is drinking water. No symptoms.",
                                             "reason": "All clear.", "needs_human_today": False, "ac_status": "working",
                                             "symptoms": [], "memory_summary": "AC working; no symptoms."})
        elif outcome == "no_answer":
            c.update(call_status="no_answer", risk_level="no_answer", attempt=2, risk_reasons=["did not answer 3 calls"])
        else:
            reason = {"warning_ac": ("AC not working", "no", "yes", []),
                      "warning_dizzy": ("symptoms: dizziness, headache", "yes", "yes", ["dizziness", "headache"]),
                      "warning_water": ("no water", "yes", "no", [])}[outcome]
            note = {"warning_ac": f"{first}'s AC stopped this morning and the house is getting hot. {first} feels okay "
                                  "so far and would take a ride to the library cooling center.",
                    "warning_dizzy": f"{first} has a headache and feels dizzy even with the AC on. Told to drink water "
                                     "and rest in the coolest room; callback booked in 30 minutes.",
                    "warning_water": f"{first} hasn't had much water today and sounded tired. Reminded to drink a "
                                     "glass now; family asked to check in."}[outcome]
            c.update(call_status="completed", risk_level="warning", risk_reasons=[reason[0]], ac_working=reason[1],
                     water=reason[2], symptoms=reason[3],
                     case_note={"summary": note, "reason": reason[0],
                                "needs_human_today": True, "ac_status": "broken" if reason[1] == "no" else "working",
                                "symptoms": reason[3], "memory_summary": reason[0]})
            db.alerts.insert_one({"resident_id": rid, "resident_name": f"{first} {last}", "playbook": "resident",
                                  "level": "warning", "reason": reason[0], "notified": ["family contact"],
                                  "created_at": started + dt.timedelta(minutes=3), "acknowledged_by": None,
                                  "resolved_at": started + dt.timedelta(minutes=25), "demo": True})
        db.checkins.insert_one(c)
    print(f"demo population: {len(OUTCOMES)} residents with today's check-ins (demo=True, no phones)")


if __name__ == "__main__":
    main()
