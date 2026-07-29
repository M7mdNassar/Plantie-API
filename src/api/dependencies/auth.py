# src/api/dependencies/auth.py
"""Single source of truth for authenticating a request.

The old version verified the JWT and looked the user up in Supabase TWICE
per request: once in a global `auth_middleware`, and again in the
`verify_token` dependency used by the chat routes. This version does it
once: verify the Supabase JWT (via a cached JWKS), resolve + cache the app
user record, then apply the per-user rate limit — all in a single pass.

There is no "DEBUG bypass" here on purpose: real chat routes always require
a valid token. The old code let ANY unauthenticated caller hit the paid LLM
in DEBUG mode, which is unsafe to ship. If you need an auth-free endpoint
for local testing, use src/api/routes/test_chat.py, which is only mounted
when DEBUG=true (see src/main.py).
"""

import time
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.jwk import construct

from src.api.middleware.rate_limit import rate_limiter
from src.config import get_settings
from src.services.supabase.database import DatabaseService

settings = get_settings()
security = HTTPBearer()

JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
JWKS_CACHE_TTL = 3600  # 1 hour

_jwks_cache: list[dict] = []
_jwks_cache_time: float = 0.0
_http_client = httpx.AsyncClient(timeout=10.0)

# Cache resolved user records briefly so a burst of requests from the same
# user doesn't cost a Supabase round trip each time.
_user_cache: TTLCache = TTLCache(maxsize=4096, ttl=60)


async def _get_jwks(force: bool = False) -> list[dict]:
    global _jwks_cache, _jwks_cache_time
    now = time.time()
    if force or not _jwks_cache or now - _jwks_cache_time > JWKS_CACHE_TTL:
        resp = await _http_client.get(
            JWKS_URL, headers={"apikey": settings.SUPABASE_ANON_KEY}
        )
        resp.raise_for_status()
        _jwks_cache = resp.json().get("keys", [])
        _jwks_cache_time = now
    return _jwks_cache


async def _get_jwk(kid: str) -> dict:
    keys = await _get_jwks()
    for key in keys:
        if key.get("kid") == kid:
            return key
    # Possible key rotation — force one refresh before giving up.
    keys = await _get_jwks(force=True)
    for key in keys:
        if key.get("kid") == kid:
            return key
    raise HTTPException(status_code=401, detail="No matching signing key found")


async def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT using JWKS public keys."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Missing kid")

        jwk = await _get_jwk(kid)
        public_key = construct(jwk)

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTClaimsError as e:
        raise HTTPException(status_code=401, detail=f"Invalid claims: {e}")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def _db(request: Request) -> DatabaseService:
    return request.app.state.db


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = await verify_supabase_token(credentials.credentials)
    auth_user_id: Optional[str] = payload.get("sub")
    if not auth_user_id:
        raise HTTPException(status_code=401, detail="Missing user ID")

    user_data = _user_cache.get(auth_user_id)
    if user_data is None:
        user_data = await _db(request).get_user_by_auth_id(auth_user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        _user_cache[auth_user_id] = user_data

    if not rate_limiter.check(user_data["id"]):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Please try again later."
        )

    return {
        "user_id": user_data["id"],
        "auth_user_id": auth_user_id,
        "user_data": user_data,
    }