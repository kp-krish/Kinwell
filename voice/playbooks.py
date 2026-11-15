"""Playbooks: the per-use-case config the engine runs.

A playbook defines the questions, red flags and escalation roles. Adding a use
case means adding an entry here, not new code.
"""

PLAYBOOKS = {
    "resident": {
        "label": "Kinwell heat check-in",
        "questions": [
            "Is your air conditioning working right now?",
            "How hot does it feel inside your home?",
            "Have you been drinking water today?",
            "Are you feeling any dizziness, headache, nausea, or confusion?",
        ],
        "escalation_roles": ["family", "backup", "caseworker"],
        "max_retries": 2,
        "retry_minutes": 15,
        "target_minutes": 3,
    },
    "crew": {
        "label": "Kinwell crew check",
        "questions": [
            "Have you had water in the last hour?",
            "Have you had a shade or rest break since your last check-in?",
            "Any headache, dizziness, nausea, or cramps?",
            "Is anyone on your crew looking unwell?",
        ],
        "escalation_roles": ["supervisor", "backup"],
        "max_retries": 1,
        "retry_minutes": 10,
        "target_minutes": 1.5,
    },
}

# Cold-weather version of the resident check-in (NWS Extreme Cold / Wind Chill alerts).
COLD_QUESTIONS = [
    "Is your heat working right now?",
    "About how warm is it inside your home?",
    "Do you have power and gas or other fuel for heat?",
    "Are you using an oven, stove, grill, or generator indoors to keep warm?",
    "Are you shivering a lot, or feeling numb, very sleepy, or confused?",
]

# Consent call: asks permission before any check-ins start.
CONSENT = {
    "label": "Kinwell",
    "max_retries": 1,
    "retry_minutes": 15,
}


def questions_for(playbook: str, hazard: str = "heat") -> list[str]:
    if playbook == "resident" and hazard == "cold":
        return COLD_QUESTIONS
    return PLAYBOOKS[playbook]["questions"]


# NWS alert events that start check-in calls, by hazard. Watches are shown, not called on.
HEAT_EVENTS = {"Extreme Heat Warning", "Excessive Heat Warning", "Heat Advisory"}
COLD_EVENTS = {"Extreme Cold Warning", "Cold Weather Advisory", "Wind Chill Warning", "Wind Chill Advisory"}
WATCH_EVENTS = {"Extreme Heat Watch", "Excessive Heat Watch", "Extreme Cold Watch", "Wind Chill Watch"}


def hazard_of(event: str) -> str | None:
    e = event or ""
    if e in HEAT_EVENTS or "Heat" in e:
        return "heat"
    if e in COLD_EVENTS or "Cold" in e or "Wind Chill" in e:
        return "cold"
    return None


# Nova 2 Sonic voices per language.
VOICES = {
    "en": "tiffany",
    "es": "lupe",
    "hi": "kiara",
}

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "hi": "Hindi"}
