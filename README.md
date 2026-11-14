# HeatCheck

**HeatCheck phones people on dangerous heat days, in their language, on any phone, and gets help moving the moment something is wrong.**

Built at sunhacks 9.0 (Nov 14 to 15, 2026).

Maricopa County confirmed 645 heat deaths in 2023 and 608 in 2024. Many people died alone at home, and more than three quarters of 2024 deaths happened outdoors. During a record heat wave, county staff phoned 93 vulnerable clients a week by hand. HeatCheck makes that check-in call to thousands of people on the same afternoon, and only pulls in a human when someone needs one.

## What it does

On an NWS heat warning, HeatCheck calls every enrolled person. Two playbooks run on one engine:

| | Residents | Crew Check (outdoor workers) |
|---|---|---|
| Who | Older adults, people living alone, homes at risk of AC failure | Roofing and construction crews |
| Questions | AC working? How hot inside? Drinking water? Dizziness, headache, nausea, confusion? | Water in the last hour? Shade or rest break? Symptoms? Coworker unwell? |
| Escalation | Family, then caseworker | Supervisor, then backup |
| Privacy | Family sees alerts for their person | Supervisor sees answers only when a red flag or missed check-in fires |

During the call the agent:
- speaks naturally and handles interruptions (English and Spanish tested; a Hindi voice is configured)
- remembers earlier calls ("Earlier you told me your AC stopped. Is it still off?")
- offers the nearest open cooling center with **today's real hours**, read from the web that morning
- says "call 911 now" and alerts every contact at once for heat-stroke signs

After the call, the escalation rules run in plain code, Gemini writes a case note, and staff see everything on a live dashboard with a ranked list of who needs a human call.

## Architecture

```
NWS heat alert ─▶ EventBridge Scheduler ─▶ Lambda risk engine ─┐
Dashboard "Simulate heat warning" ─────────────────────────────┤
                                                               ▼
Phone ◀─ Twilio Voice ─wss─▶ CloudFront ─▶ ALB ─▶ ECS Fargate voice server ─▶ Amazon Nova 2 Sonic (Bedrock)
                                                    │   tools: record_checkin, flag_risk,
                                                    │   find_cooling_center, find_ac_assistance, ...
                                                    ├─▶ MongoDB Atlas (people, check-ins, alerts, resources; $geoNear, TTL)
                                                    ├─▶ Supermemory (one memory space per person)
                                                    ├─▶ Gemini (case notes, ranked briefing)
                                                    └─▶ Step Functions escalation ladder ─▶ Lambda ─▶ alert calls, follow-up calls

Resource Scout (TinyFish web agent, Maritime-hosted, sleeps until woken) ─▶ Atlas (live cooling-center hours)
React dashboard on AWS Amplify ◀── live state from the voice service
```

| Component | Built with |
|---|---|
| Voice agent | Amazon Nova 2 Sonic (`amazon.nova-2-sonic-v1:0`), bidirectional stream, 8 kHz phone audio both ways |
| Phone bridge | Twilio Programmable Voice with Media Streams; answering-machine detection |
| Voice service | Python (FastAPI) on ECS Fargate behind ALB and CloudFront (HTTPS/WSS) |
| Escalation | AWS Step Functions (wait-for-callback task token), Lambda |
| Risk engine | EventBridge Scheduler and Lambda polling the NWS alerts API for Maricopa County |
| Database | MongoDB Atlas: 2dsphere index and `$geoNear` for the nearest open cooling center; TTL index expires transcripts |
| Memory | Supermemory API v5, one namespace per person |
| Web agent | TinyFish Agent API reads library and cooling-center pages; Amazon Location Service geocodes |
| Agent hosting | Maritime (Resource Scout sleeps until a heat warning or a caseworker wakes it) |
| Text AI | Gemini (structured JSON case notes and the morning briefing) |
| Dashboard | React, Vite, TypeScript, Tailwind, MapLibre, AWS Amplify Hosting |

## Safety and privacy design

- **Rules decide emergencies, not the model.** Sonic only reports facts through tools. `voice/rules.py` decides who gets alerted, so outcomes are predictable and auditable.
- **Unconfirmed is never "safe."** Voicemail, a dropped call, or a call that ends before answers goes to the no-answer path: retry, then the escalation ladder.
- **Guards in code.** The agent cannot hang up before recording answers; crew water and break reminders cannot alert a supervisor; a daily call cap per person stops runaway calling.
- **Consent first.** Calls go only to enrolled numbers, and the agent says it is automated in its first sentence.
- **Data minimization.** No call audio is stored; transcripts expire after 30 days through a TTL index; memory holds short safety summaries only.
- **Live data honesty.** The agent quotes only cooling centers and hours from Resource Scout records, and never invents places or hours.
- **Screening, not diagnosis.** Questions follow common heat-illness warning signs; heat-stroke signs always produce "call 911 now."

## Repository layout

```
voice/       voice service: Twilio bridge, Nova Sonic session, tools, rules, memory, notes, API
scout/       Resource Scout: TinyFish agent, HTTP wrapper and Dockerfile for Maritime
dashboard/   React dashboard
infra/       CloudFormation: voice.yaml (Fargate, ALB, CloudFront), escalation.yaml (Step Functions, Lambda, Scheduler)
scripts/     seeding, demo data, simulated caller, deploy scripts
```

## Running it

Requirements: Python 3.13, Node 22+, Docker, an AWS account with Bedrock access to Nova 2 Sonic in us-west-2, plus Twilio, MongoDB Atlas, Gemini, Supermemory and TinyFish keys.

```bash
cp .env.example .env                          # fill in keys
python -m venv .venv && .venv/Scripts/pip install -r voice/requirements.txt
python scripts/seed_atlas.py                  # indexes and demo people
python -m scout.resource_scout                # live cooling-center hours
python scripts/sim_call.py en_warning         # full simulated call, no phone needed
bash scripts/deploy_voice.sh                  # Fargate (after infra/voice.yaml is deployed once)
python scripts/deploy_dashboard.py https://<voice-cloudfront-domain>
```

`scripts/sim_call.py` runs a complete check-in without a phone: Gemini plays the caller from a persona, Amazon Polly speaks the replies as 8 kHz audio into the same Nova Sonic session, and contact alerts run in dry-run mode. Scenarios: `en_warning`, `en_followup`, `en_clear`, `es_warning`, `crew_ok`.

The dashboard's map includes a clearly labeled synthetic demo population (`scripts/demo_population.py`, records flagged `demo`, no phone numbers). Remove it with `--remove`.

## Limits and honest notes

- Nova Sonic allows 20 concurrent sessions per region; calls are queued by risk and can spread across regions.
- Cooling-center data in November comes from public library hours (Phoenix and Tempe). More sources, such as the county Heat Relief Network in summer, are added in `scout/sources.json`.
- Alerts to contacts go by voice call; US text messages need a registered sender.
- A typical 3-minute check-in costs about $0.10 (Twilio plus Nova Sonic).
