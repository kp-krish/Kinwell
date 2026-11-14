"""Place a single Twilio test call to DEMO_PHONE_NUMBER with a spoken message.

Usage: python scripts/test_call.py
Reads credentials from .env in the repo root. Never prints secrets.
"""
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(path: pathlib.Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


def main() -> int:
    env = load_env(ROOT / ".env")
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "DEMO_PHONE_NUMBER"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return 1

    sid = env["TWILIO_ACCOUNT_SID"]
    twiml = (
        "<Response><Say voice=\"Polly.Joanna\">"
        "Hello, this is the HeatCheck test call. "
        "If you can hear this, Twilio is working. Goodbye."
        "</Say></Response>"
    )
    data = urllib.parse.urlencode({
        "To": env["DEMO_PHONE_NUMBER"],
        "From": env["TWILIO_PHONE_NUMBER"],
        "Twiml": twiml,
    }).encode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", data=data, method="POST"
    )
    token = base64.b64encode(f"{sid}:{env['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}")
        print(f"Twilio error {e.code}: {err.get('code')} {err.get('message')}")
        return 1

    print(f"Call queued: sid={body['sid']} status={body['status']} to=...{body['to'][-4:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
