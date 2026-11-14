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

def _mongo_uri() -> str:
    """Fill <db_username>/<db_password> placeholders from MONGODB_USER/MONGODB_PASSWORD."""
    from urllib.parse import quote_plus
    uri = os.environ.get("MONGODB_URI", "")
    user = os.environ.get("MONGODB_USER", "")
    pw = os.environ.get("MONGODB_PASSWORD", "")
    if user:
        uri = uri.replace("<db_username>", quote_plus(user)).replace("<username>", quote_plus(user))
    if pw:
        uri = uri.replace("<db_password>", quote_plus(pw)).replace("<password>", quote_plus(pw))
    return uri


def _first(*names: str) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    return ""


MONGODB_URI = _mongo_uri()
GEMINI_API_KEY = _first("GEMINI_API_KEY", "GEMINI_API")
SUPERMEMORY_API_KEY = _first("SUPERMEMORY_API_KEY", "SUPERMEMORY_API")
TINYFISH_API_KEY = _first("TINYFISH_API_KEY", "TINYFISH_API")

# Safety: max outbound calls per person per day (runaway protection).
DAILY_CALL_CAP = int(os.environ.get("DAILY_CALL_CAP", "6"))
