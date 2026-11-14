"""Build the dashboard against the deployed API and publish it to AWS Amplify Hosting
(manual zip deployment, so Amplify needs no access to the private GitHub repo).

Usage: python scripts/deploy_dashboard.py https://<cloudfront-domain>
"""
import io
import os
import pathlib
import subprocess
import sys
import time
import zipfile

import boto3
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboard"
REGION = os.environ.get("INFRA_REGION", "us-east-2")
APP_NAME = "heatcheck-sunhacks-dashboard"


def main(api_base: str):
    env = dict(os.environ, VITE_API_BASE=api_base)
    subprocess.run("npm run build", cwd=DASH, shell=True, check=True, env=env)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (DASH / "dist").rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(DASH / "dist").as_posix())

    amp = boto3.client("amplify", region_name=REGION)
    apps = [a for a in amp.list_apps()["apps"] if a["name"] == APP_NAME]
    if apps:
        app_id = apps[0]["appId"]
    else:
        app_id = amp.create_app(name=APP_NAME, platform="WEB",
                                customRules=[{"source": "/<*>", "target": "/index.html", "status": "404-200"}],
                                tags={"project": "heatcheck-sunhacks"})["app"]["appId"]
        amp.create_branch(appId=app_id, branchName="main", stage="PRODUCTION")
    dep = amp.create_deployment(appId=app_id, branchName="main")
    httpx.put(dep["zipUploadUrl"], content=buf.getvalue(), timeout=120).raise_for_status()
    job = amp.start_deployment(appId=app_id, branchName="main", jobId=dep["jobId"])["jobSummary"]
    for _ in range(60):
        st = amp.get_job(appId=app_id, branchName="main", jobId=job["jobId"])["job"]["summary"]["status"]
        if st in ("SUCCEED", "FAILED", "CANCELLED"):
            break
        time.sleep(3)
    print("status:", st)
    print("url: https://main." + amp.get_app(appId=app_id)["app"]["defaultDomain"])


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"))
