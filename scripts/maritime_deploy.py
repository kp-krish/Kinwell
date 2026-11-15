"""Deploy Resource Scout to Maritime from a zip (no public repo needed).

Usage:
  python scripts/maritime_deploy.py deploy     # create or redeploy
  python scripts/maritime_deploy.py status
  python scripts/maritime_deploy.py logs
  python scripts/maritime_deploy.py wake       # start the agent and trigger a scout run

Secrets come from .env and are stored as Maritime secret env vars. The agent id is
kept in scout/maritime_agent.json (not secret).
"""
import io
import json
import os
import pathlib
import secrets
import sys
import time
import zipfile

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from voice import config  # noqa: E402  (loads .env, resolves Mongo URI)

API = "https://api.maritime.sh"
KEY = os.environ.get("MARITIME_API_KEY") or os.environ.get("MARITIME_API", "")
H = {"Authorization": f"Bearer {KEY}"}
STATE = ROOT / "scout" / "maritime_agent.json"
NAME = "heatcheck-resource-scout"
FILES = ["Dockerfile", "requirements.txt", "resource_scout.py", "server.py", "sources.json"]


def scout_token() -> str:
    tok = os.environ.get("SCOUT_TOKEN")
    if tok:
        return tok
    tok = secrets.token_urlsafe(24)
    with open(ROOT / ".env", "a", encoding="utf-8") as f:
        f.write(f"\nSCOUT_TOKEN={tok}\n")
    os.environ["SCOUT_TOKEN"] = tok
    print("generated SCOUT_TOKEN and appended it to .env")
    return tok


def req(method, path, **kw):
    r = httpx.request(method, API + path, headers=H, timeout=120, **kw)
    if r.status_code >= 300:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:800]}")
    return r.json() if r.content else {}


def build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            z.write(ROOT / "scout" / f, f)
    return buf.getvalue()


def env_vars() -> list[dict]:
    return [
        {"key": "MONGODB_URI", "value": config.MONGODB_URI, "isSecret": True},
        {"key": "TINYFISH_API_KEY", "value": config.TINYFISH_API_KEY, "isSecret": True},
        {"key": "SCOUT_TOKEN", "value": scout_token(), "isSecret": True},
    ]


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def deploy():
    up = req("POST", "/api/upload/zip", files={"file": ("scout.zip", build_zip(), "application/zip")})
    s3_key = up.get("s3Key") or up.get("s3_key") or up.get("key")
    print("uploaded:", {k: v for k, v in up.items() if k != "files"})
    st = load_state()
    if not st.get("agent_id"):
        agent = req("POST", "/api/agents", json={
            "name": NAME,
            "description": "Kinwell Resource Scout: TinyFish reads cooling-center pages; sleeps until a heat warning wakes it.",
            "framework": "custom",
            "exposedPort": 8000,
            "healthCheckPath": "/health",
            "hasWebUi": False,
            "publicWeb": True,
            "idleTtlSeconds": 300,
            "uploadS3Key": s3_key,
            "initialEnvVars": env_vars(),
        })
        st = {"agent_id": agent.get("id") or agent.get("agentId") or agent.get("agent_id"), "name": NAME}
        STATE.write_text(json.dumps(st, indent=1))
        print("created agent:", st["agent_id"], "status:", agent.get("status"))
    dep = req("POST", "/api/deploy", json={"agentId": st["agent_id"], "source": "zip", "uploadS3Key": s3_key})
    print("deployment:", json.dumps(dep)[:400])


def status():
    st = load_state()
    a = req("GET", f"/api/agents/{st['agent_id']}")
    print(json.dumps({k: a.get(k) for k in ("id", "name", "status", "errorMessage", "publicUrl", "url",
                                            "idleTtlSeconds", "exposedPort", "updatedAt")}, indent=1))
    deps = req("GET", f"/api/deploy/agent/{st['agent_id']}")
    items = deps if isinstance(deps, list) else deps.get("items", deps.get("deployments", []))
    for d in items[:3]:
        print("deploy:", {k: d.get(k) for k in ("id", "status", "error", "errorMessage", "createdAt")})


def logs():
    st = load_state()
    out = req("GET", f"/api/agents/{st['agent_id']}/logs", params={"lines": 80})
    lines = out if isinstance(out, list) else out.get("logs", out)
    print(lines if isinstance(lines, str) else "\n".join(str(l) for l in lines))


def wake(sources=None):
    st = load_state()
    t0 = time.time()
    print("start:", req("POST", f"/api/agents/{st['agent_id']}/start"))
    url = f"{API}/a/{st['agent_id']}"
    for _ in range(40):
        try:
            r = httpx.get(url + "/health", timeout=10)
            if r.status_code == 200 and r.json().get("ok"):
                break
        except Exception:
            pass
        time.sleep(3)
    print(f"awake after {time.time() - t0:.0f}s")
    r = httpx.post(url + "/run", json={"trigger": "heat_warning", "sources": sources},
                   headers={"Authorization": f"Bearer {scout_token()}"}, timeout=30)
    print("run:", r.status_code, r.text[:300])


if __name__ == "__main__":
    if not KEY:
        raise SystemExit("MARITIME_API (or MARITIME_API_KEY) missing in .env")
    {"deploy": deploy, "status": status, "logs": logs, "wake": wake}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
