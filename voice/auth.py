"""Family accounts: verify Amazon Cognito ID tokens and keep a users table in Atlas."""
from __future__ import annotations

import asyncio
import functools
import logging
import os

from fastapi import Header, HTTPException

from .store import get_store, now

log = logging.getLogger("auth")

POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
REGION = POOL_ID.split("_", 1)[0] if POOL_ID else ""
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"


@functools.lru_cache(maxsize=1)
def _jwks():
    import jwt
    return jwt.PyJWKClient(f"{ISSUER}/.well-known/jwks.json", cache_keys=True)


def _verify(token: str) -> dict:
    import jwt
    key = _jwks().get_signing_key_from_jwt(token).key
    claims = jwt.decode(token, key, algorithms=["RS256"], audience=CLIENT_ID, issuer=ISSUER)
    if claims.get("token_use") != "id":
        raise jwt.InvalidTokenError("not an ID token")
    return claims


async def current_user(authorization: str | None = Header(None)) -> dict:
    """FastAPI dependency: the signed-in family member's users row (created on first use)."""
    if not POOL_ID or not CLIENT_ID:
        raise HTTPException(503, "sign-in is not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "sign in required")
    try:
        claims = await asyncio.to_thread(_verify, authorization.split(" ", 1)[1].strip())
    except Exception as e:
        log.info("token rejected: %s", e)
        raise HTTPException(401, "session expired, please sign in again")
    store = get_store()
    user = await store.get("users", claims["sub"])
    if not user:
        email = claims.get("email", "")
        user = {"_id": claims["sub"], "email": email,
                "name": claims.get("name") or email.split("@")[0].title(),
                "phone": claims.get("phone_number") or "", "created_at": now()}
        await store.insert("users", user)
        log.info("new family user %s", user["_id"])
    return user
