"""Create/update the heatcheck/app secret in AWS Secrets Manager from .env (values never printed)."""
import json
import os
import pathlib
import sys

import boto3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from voice import config  # noqa: E402

REGION = os.environ.get("INFRA_REGION", "us-east-2")
NAME = "heatcheck/app"

values = {
    "TWILIO_ACCOUNT_SID": config.TWILIO_ACCOUNT_SID,
    "TWILIO_AUTH_TOKEN": config.TWILIO_AUTH_TOKEN,
    "TWILIO_PHONE_NUMBER": config.TWILIO_PHONE_NUMBER,
    "DEMO_PHONE_NUMBER": config.DEMO_PHONE_NUMBER,
    "MONGODB_URI": config.MONGODB_URI,
    "GEMINI_API_KEY": config.GEMINI_API_KEY,
    "SUPERMEMORY_API_KEY": config.SUPERMEMORY_API_KEY,
    "MARITIME_API_KEY": os.environ.get("MARITIME_API_KEY") or os.environ.get("MARITIME_API", ""),
    "SCOUT_TOKEN": os.environ.get("SCOUT_TOKEN", ""),
    "INTERNAL_TOKEN": os.environ.get("INTERNAL_TOKEN", ""),
    "DASHBOARD_KEY": os.environ.get("DASHBOARD_KEY", ""),
}
missing = [k for k, v in values.items() if not v]
sm = boto3.client("secretsmanager", region_name=REGION)
try:
    arn = sm.describe_secret(SecretId=NAME)["ARN"]
    sm.put_secret_value(SecretId=NAME, SecretString=json.dumps(values))
    print("updated", arn)
except sm.exceptions.ResourceNotFoundException:
    arn = sm.create_secret(Name=NAME, SecretString=json.dumps(values),
                           Tags=[{"Key": "project", "Value": "heatcheck"}])["ARN"]
    print("created", arn)
if missing:
    print("warning: empty values for", ", ".join(missing))
