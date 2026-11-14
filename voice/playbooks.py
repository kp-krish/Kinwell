"""Playbooks: the per-use-case config the engine runs.

A playbook defines the questions, red flags and escalation roles. Adding a use
case means adding an entry here, not new code.
"""

PLAYBOOKS = {
    "resident": {
        "label": "Valley heat check-in",
        "questions": [
            "Is your air conditioning working right now?",
            "How hot does it feel inside your home?",
            "Have you been drinking water today?",
            "Are you feeling any dizziness, headache, nausea, or confusion?",
        ],
        "escalation_roles": ["family", "caseworker"],
        "max_retries": 2,
        "retry_minutes": 15,
        "target_minutes": 3,
    },
    "crew": {
        "label": "HeatCheck crew check",
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

# Nova 2 Sonic voices per language.
VOICES = {
    "en": "tiffany",
    "es": "lupe",
    "hi": "kiara",
}

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "hi": "Hindi"}
