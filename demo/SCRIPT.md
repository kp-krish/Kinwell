# Kinwell demo video: script and shot list

Target length: about 2:50. Format: 1920x1080, 30 fps. Phone clips are 780x1688; place them in a phone frame
or centered on a dark background (#14121B) beside the desktop footage.

Voiceover: calm, warm, unhurried (one AI voice for the narrator). Lines in "quotes" under VO are read
as written. Lines marked CALL are real call audio or captions of it.

Clips live in `demo/clips/` (re-record any time with `.venv/Scripts/python.exe demo/record_clips.py [scene]`).
Shots marked **YOU** need a real phone and must be captured by a person (see "Shots to capture live" below).

---

## 1. Hook (0:00 to 0:12)

Visual: black, then slow fade to `dash_overview.mp4` 0:00 to 0:04 (the "112° high today" hero), soft blur.
On-screen text: **Every summer, people die alone at home in the heat. Every winter, in the cold.**

VO: "Every summer, older adults die alone at home in the heat. Most of them had someone who would have
come, if only they'd known in time."

## 2. A daughter adds her dad (0:12 to 0:40)

Visual: `family_assistant_phone.mp4` from 0:02 to 0:58, sped up 2x (about 28 s). Phone frame, centered.
Hold the last frame (the "Here's what I have" summary) for 1.5 s.

VO: "Kinwell starts with family. Maria tells the assistant she wants to add her dad. It asks one thing at a
time: his number, his address, the language he speaks, and a backup contact. It works by voice or text, and
it double-checks anything that doesn't look right."

## 3. Permission first (0:40 to 0:52)

Audio: `call1_permission_mixed.mp3` (real call, 29 s; trim to the intro, the question and "yes").
Visual: your dashboard screen recording `Kinwell Team - Google Chrome 2026-11-15 00-38-07.mp4`, or a dark card
with the caption lines below typed on.

CALL (captions):
> "This is an automated call from Kinwell. Maria signed you up… Is it okay if we call you on those days?"
> "Yes."

VO: "Before any check-ins, Kinwell calls her dad and asks for his permission. Nothing starts until he says yes."

## 4. A heat warning hits (0:52 to 1:02)

Visual: **YOU** desktop screen recording of the team dashboard, clicking **Simulate heat**, cutting to the phone
ringing. Fallback: `dash_overview.mp4` 0:00 to 0:06.

VO: "When the National Weather Service issues an extreme heat or cold warning anywhere someone is enrolled,
Kinwell's risk engine starts calls automatically."

## 5. The check-in call (1:02 to 1:38)

Audio: `call2_heat_checkin_take3_mixed.mp3` (real call, 54 s). Start at about 0:06 to skip the repeated
greeting; tighten the pauses between turns. Separate voice tracks: `_ch1.wav` and `_ch2.wav`.
Visual: your dashboard screen recording `Kinwell Team - Google Chrome 2026-11-15 00-59-19.mp4` (John moves to
Need you), then `dash_call_detail.mp4` 0:10 to 0:29, with captions.

CALL (what was said):
> Agent: "Hi, it's Kinwell checking on you. Is your air conditioning working right now?"
> John: "Yes, it's working."
> Agent: "How hot does it feel inside your home?"
> John: "I think it's about ninety-five degrees."
> Agent: "Have you been drinking water today?" / John: "Yes."
> Agent: "Are you feeling any dizziness, headache, nausea, or confusion?"
> John: "I feel a little dizzy."
> Agent: "The nearest cooling center is Tempe Public Library, about 3 miles away. It is closed right now and
> opens at 9 AM today. Until then, try staying in the coolest room, taking a cool shower, or visiting a
> friend's place. Would a ride there help?"
> John: "Yes."
> Agent: "I'll call back soon to check on you. Goodbye, John."

VO (over the end of the call): "The agent runs on Amazon Nova 2 Sonic, speech to speech in real time. It asks
short questions, notices warning signs, and finds the nearest cooling center from records our web agent
checked today. Ninety-five degrees inside counts as a warning even when the AC says it's on."

## 6. Family hears right away (1:38 to 1:50)

Audio: Twilio does not record the alert call; have the AI voice read "This is an automated alert from Kinwell
about John. John's home is very hot, about 95 degrees inside, and he feels dizzy." Visual:
`family_home_phone.mp4` 0:08 to 0:20 (Rosa's status page).

VO: "Seconds after the call, the family gets a phone alert, and the family site shows exactly what happened."

## 7. The team's view (1:50 to 2:28)

a) `dash_overview.mp4` 0:00 to 0:12, then 0:20 to 0:29 (Gemini ranking appears).
VO: "Caseworkers see everyone on one board: who needs a human, what Kinwell is already handling, and who's
safe. Gemini ranks who to call first."

b) `dash_call_detail.mp4` 0:02 to 0:16.
VO: "Every call becomes a case note, the answers, who's been told, and the full transcript. Kinwell
remembers earlier calls with Supermemory, so the next call can ask: is your AC still broken?"

c) `dash_map.mp4` 0:02 to 0:14 (hover on a cooling center card).
VO: "Cooling and warming centers come from a TinyFish web agent that reads city sites for today's hours,
stored in MongoDB Atlas with geospatial search."

d) `dash_phone.mp4` 0:00 to 0:08, phone frame.
VO: "And whoever is on call gets the same board on their phone."

## 8. Not just heat (2:28 to 2:38)

Visual: `family_home_desktop.mp4` 0:03 to 0:10 (cold mode, "55° low tonight").

VO: "Kinwell works in the cold too, with questions about the heat being on, power and gas, and carbon monoxide
from ovens or generators used for warmth."

## 9. How it's built (2:38 to 2:48)

Visual: dark card, logos or names in a grid:
Amazon Nova 2 Sonic (Bedrock) · Step Functions · Cognito · Amazon Location · Amplify · ECS Fargate ·
MongoDB Atlas · Supermemory · Gemini · TinyFish on Maritime · National Weather Service API · Twilio

VO: "Built on AWS, MongoDB Atlas, Supermemory, Gemini, and TinyFish."

## 10. Close (2:48 to 2:52)

Visual: Kinwell logo (`dashboard/public/icon.svg`) and wordmark on #14121B.
On-screen text: **Kinwell. Know they're okay on the hottest and coldest days.**

VO: "Kinwell. Know they're okay on the hottest and coldest days."

---

## Shots to capture live (**YOU**)

1. Save the Twilio number in your phone as **Kinwell** first, so the incoming-call screen shows the name and
   call screening doesn't answer first.
2. Phone screen: iPhone Control Center, then Screen Recording. iOS does not record call audio, so put the call on
   **speaker** and record the audio with your laptop (Windows Voice Recorder) at the same time.
3. Desktop: Win+G (Xbox Game Bar), then Record, on the dashboard while you press **Simulate heat**.
4. Order: press Simulate heat, then answer on speaker. Use the same answers as in section 5. After you hang up,
   the family alert call comes in about 2 seconds later.

## Clip inventory

| Clip | Length | Size | What it shows |
|---|---|---|---|
| dash_overview.mp4 | 0:30 | 1920x1080 | Live heat-day board, scroll, Gemini "Rank now" |
| dash_call_detail.mp4 | 0:30 | 1920x1080 | Open John's call: case note, answers, who's been told, transcript |
| dash_map.mp4 | 0:22 | 1920x1080 | Map, hover cards on three cooling centers, zoom |
| dash_tabs.mp4 | 0:25 | 1920x1080 | People, Crews, Cooling & warming tabs |
| dash_phone.mp4 | 0:19 | 780x1688 | On-call phone view, map tab, everyone tab |
| family_home_phone.mp4 | 0:25 | 780x1688 | Sign in, home, Rosa's status, heat/cold toggle |
| family_assistant_phone.mp4 | 0:59 | 780x1688 | Assistant adds "Miguel" end to end (placeholder numbers) |
| family_home_desktop.mp4 | 0:35 | 1920x1080 | Same as phone, desktop layout (cold mode) |
| family_assistant_desktop.mp4 | 1:25 | 1920x1080 | Assistant on desktop |

All data on screen is demo data (residents flagged demo, no phone numbers) or test calls to the team's own
phone. Phone numbers typed in the assistant are 555 placeholders.
