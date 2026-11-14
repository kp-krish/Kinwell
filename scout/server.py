"""HTTP wrapper so Resource Scout can run as a Maritime agent.

Maritime keeps the agent asleep when idle (idleTtlSeconds). The risk engine or a
caseworker wakes it, calls POST /run, and it goes back to sleep after the run.
"""
from __future__ import annotations

import datetime as dt
import hmac
import os
import threading

from fastapi import FastAPI, Header, HTTPException

from resource_scout import scout

app = FastAPI(title="HeatCheck Resource Scout")
TOKEN = os.environ.get("SCOUT_TOKEN", "")
_state = {"running": False, "last": None, "started_at": None}
_lock = threading.Lock()


def _check(auth: str | None) -> None:
    if not TOKEN or not auth or not hmac.compare_digest(auth.removeprefix("Bearer ").strip(), TOKEN):
        raise HTTPException(401, "unauthorized")


def _run(sources):
    try:
        _state["last"] = scout(sources)
    except Exception as e:  # keep serving; the run log in Atlas has details
        _state["last"] = {"error": str(e)}
    finally:
        _state["running"] = False


@app.get("/health")
def health():
    return {"ok": True, "running": _state["running"], "started_at": _state["started_at"]}


@app.post("/run")
def run(payload: dict | None = None, authorization: str | None = Header(None)):
    _check(authorization)
    with _lock:
        if _state["running"]:
            return {"status": "already_running", "started_at": _state["started_at"]}
        _state["running"] = True
        _state["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    sources = (payload or {}).get("sources")
    threading.Thread(target=_run, args=(sources,), daemon=True).start()
    return {"status": "started", "trigger": (payload or {}).get("trigger", "manual")}


@app.get("/last")
def last(authorization: str | None = Header(None)):
    _check(authorization)
    return _state
