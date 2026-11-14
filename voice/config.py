"""Settings loaded from environment (and .env locally)."""
import os
import pathlib

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
os.environ.setdefault("AWS_REGION", AWS_REGION)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
DEMO_PHONE_NUMBER = os.environ.get("DEMO_PHONE_NUMBER", "")

# Public https host (no scheme) that Twilio can reach, e.g. abc.trycloudflare.com
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "")

MONGODB_URI = os.environ.get("MONGODB_URI", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPERMEMORY_API_KEY = os.environ.get("SUPERMEMORY_API_KEY", "")

# Safety: max outbound calls per person per day (runaway protection).
DAILY_CALL_CAP = int(os.environ.get("DAILY_CALL_CAP", "6"))
