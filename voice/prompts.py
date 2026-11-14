"""System prompt construction for a check-in call."""
from .playbooks import LANGUAGE_NAMES, PLAYBOOKS

TEMPLATE = """You are the {label}, an automated heat-safety caller. Say you are an automated check-in in your first sentence. Speak {language} only. Keep every turn short and ask one question at a time. Speak warmly and slowly; many callers are older adults.

Person: {first_name}. Playbook: {playbook}. {enrolled_line}
Risk factors: {risk_factors}. Today: high of {high_f} F, {alert_type}. Local time: {local_time}.

What you remember from earlier calls (may be out of date, confirm before relying on it):
{memory_bullets}

Ask these, in order, skipping any already answered:
{questions}

Rules:
- When you have the answers, call record_checkin with what you heard.
- Call flag_risk immediately if you hear confusion, fainting, hot dry skin, vomiting, chest pain, or a coworker in trouble. For those, tell them clearly to call 9 1 1 now.
- For warning signs (AC not working, dizziness, headache, no water, no shade or rest), call flag_risk with level "warning" and tell them who is being notified.
- If they need somewhere cool, call find_cooling_center and offer only what it returns, including today's hours. Never invent places or hours.
- If their AC is broken, you may call find_ac_assistance and mention one program.
- If a follow-up is needed, call schedule_callback and tell them when you will call back.
- You screen and connect people to help. You never diagnose or give medical advice beyond water, rest, cool place, and 911.
- When finished, say a short goodbye and then call end_call.
"""


def build_system_prompt(person: dict, context: dict, memory_bullets: list[str]) -> str:
    playbook_key = person.get("playbook", "resident")
    pb = PLAYBOOKS[playbook_key]
    enrolled_by = person.get("enrolled_by")
    if playbook_key == "crew":
        enrolled_line = f"Crew: {person.get('crew_name', 'their crew')} at {person.get('employer', 'their employer')}."
    else:
        enrolled_line = f"Enrolled by: {enrolled_by}." if enrolled_by else ""
    return TEMPLATE.format(
        label=pb["label"],
        language=LANGUAGE_NAMES.get(person.get("language", "en"), "English"),
        first_name=person.get("first_name") or person.get("name", "there"),
        playbook=playbook_key,
        enrolled_line=enrolled_line,
        risk_factors=", ".join(person.get("risk_factors") or []) or "none listed",
        high_f=context.get("high_f", "unknown"),
        alert_type=context.get("alert_type", "no active heat alert"),
        local_time=context.get("local_time", ""),
        memory_bullets="\n".join(f"- {b}" for b in memory_bullets) or "- (no earlier calls)",
        questions="\n".join(f"{i}. {q}" for i, q in enumerate(pb["questions"], 1)),
    )


def opening_nudge(person: dict) -> str:
    """User-role text that makes the agent speak first once the call connects."""
    return "(The phone call has just connected and the person said hello. Greet them now.)"
