"""Demo seed data. Phone numbers come from .env so nothing personal is committed.

Cooling-center rows are fallback seed records (source_url "seed"); Resource Scout
replaces them with live, timestamped records.
"""
from __future__ import annotations

import datetime as dt

from . import config


def _pt(lat: float, lng: float) -> dict:
    return {"type": "Point", "coordinates": [lng, lat]}


def seed_documents() -> dict[str, list[dict]]:
    demo = config.DEMO_PHONE_NUMBER
    fetched = dt.datetime.now(dt.timezone.utc).replace(hour=13, minute=2, second=0, microsecond=0)
    residents = [
        {
            "_id": "res_lopez",
            "name": "Rosa Lopez", "first_name": "Rosa",
            "phone": demo, "language": "en",
            "address": "1100 E Apache Blvd, Tempe, AZ 85281",
            "location": _pt(33.4148, -111.9180),
            "zip": "85281",
            "risk_factors": ["age 78", "lives alone", "high blood pressure"],
            "enrolled_by": "her daughter Maria",
            "playbook": "resident", "consent_at": "2026-11-10T17:00:00Z",
            "caseworker_id": "cw_1",
        },
        {
            "_id": "res_garcia",
            "name": "Ernesto Garcia", "first_name": "Ernesto",
            "phone": "", "language": "es",
            "address": "2020 W Van Buren St, Phoenix, AZ 85009",
            "location": _pt(33.4516, -112.1010),
            "zip": "85009",
            "risk_factors": ["age 84", "no car"],
            "enrolled_by": "caseworker Dana",
            "playbook": "resident", "consent_at": "2026-11-09T17:00:00Z",
            "caseworker_id": "cw_1",
        },
        {
            "_id": "wrk_luis",
            "name": "Luis Ramirez", "first_name": "Luis",
            "phone": demo, "language": "en",
            "address": "Job site, 4400 S Rural Rd, Tempe, AZ 85282",
            "location": _pt(33.3710, -111.9265),
            "zip": "85282",
            "risk_factors": ["outdoor roofing work"],
            "playbook": "crew", "crew_id": "crew_desert", "crew_name": "Roof crew 2",
            "employer": "Desert Roofing", "consent_at": "2026-11-12T15:00:00Z",
        },
    ]
    crews = [
        {
            "_id": "crew_desert", "name": "Roof crew 2", "employer": "Desert Roofing",
            "site_location": _pt(33.3710, -111.9265),
            "shift_start": "06:00", "shift_end": "15:00", "interval_min": 120,
            "supervisor_contact_id": "c_sup", "backup_contact_id": "c_backup",
        }
    ]
    contacts = [
        {"_id": "c_maria", "resident_id": "res_lopez", "name": "Maria Lopez", "role": "family",
         "phone": demo, "email": "", "escalation_order": 1},
        {"_id": "c_dana", "resident_id": "res_lopez", "name": "Dana Reyes", "role": "caseworker",
         "phone": demo, "email": "", "escalation_order": 2},
        {"_id": "c_sup", "resident_id": "wrk_luis", "name": "Sam Ortiz", "role": "supervisor",
         "phone": demo, "email": "", "escalation_order": 1},
        {"_id": "c_backup", "resident_id": "wrk_luis", "name": "Jordan Lee", "role": "backup",
         "phone": demo, "email": "", "escalation_order": 2},
    ]
    resources = [
        {"_id": "rc_tempe_lib", "type": "cooling_center", "name": "Tempe Public Library",
         "address": "3500 S Rural Rd, Tempe, AZ 85282", "location": _pt(33.3946, -111.9264),
         "hours_today": "9 AM to 7 PM", "open_today": True, "notes": "Wheelchair accessible",
         "source_url": "seed", "fetched_at": fetched},
        {"_id": "rc_burton_barr", "type": "cooling_center", "name": "Burton Barr Central Library",
         "address": "1221 N Central Ave, Phoenix, AZ 85004", "location": _pt(33.4618, -112.0738),
         "hours_today": "9 AM to 5 PM", "open_today": True, "notes": "",
         "source_url": "seed", "fetched_at": fetched},
        {"_id": "rc_mesa_main", "type": "cooling_center", "name": "Mesa Main Library",
         "address": "64 E 1st St, Mesa, AZ 85201", "location": _pt(33.4155, -111.8315),
         "hours_today": "9 AM to 6 PM", "open_today": True, "notes": "",
         "source_url": "seed", "fetched_at": fetched},
        {"_id": "rc_chandler_lib", "type": "cooling_center", "name": "Chandler Downtown Library",
         "address": "22 S Delaware St, Chandler, AZ 85225", "location": _pt(33.3022, -111.8418),
         "hours_today": "10 AM to 6 PM", "open_today": True, "notes": "",
         "source_url": "seed", "fetched_at": fetched},
        {"_id": "ac_county_wx", "type": "ac_program", "name": "Maricopa County home weatherization and AC repair help",
         "address": "", "location": _pt(33.4484, -112.0740), "open_today": True,
         "eligibility": "Income-qualified homeowners and renters in Maricopa County",
         "hours_today": "", "source_url": "seed", "fetched_at": fetched},
    ]
    return {"residents": residents, "crews": crews, "contacts": contacts, "resources": resources}
