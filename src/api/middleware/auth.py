# from fastapi import Request, HTTPException, Depends
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# import jwt
# from src.config import get_settings
# from src.services.supabase.database import DatabaseService
#
# settings = get_settings()
# db = DatabaseService()
# security = HTTPBearer()
#
# async def verify_token(
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ) -> dict:
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(
#             token,
#             settings.SUPABASE_JWT_SECRET,
#             algorithms=["HS256"],
#             options={"require": ["exp", "sub"]}
#         )
#         auth_user_id = payload["sub"]
#     except jwt.ExpiredSignatureError:
#         raise HTTPException(status_code=401, detail="Token expired")
#     except jwt.InvalidTokenError:
#         raise HTTPException(status_code=401, detail="Invalid token")
#
#     user_data = await db.get_user_by_auth_id(auth_user_id)
#     if not user_data:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     return {
#         "user_id": user_data["id"],
#         "auth_user_id": auth_user_id,
#         "user_data": user_data
#     }
#
# async def auth_middleware(request: Request, call_next):
#     path = request.url.path
#     if (path in ["/", "/docs", "/openapi.json", "/redoc"] or
#         path.startswith("/docs/") or path.startswith("/redoc/") or
#         path.startswith("/api/v1/health")):
#         return await call_next(request)
#
#     auth_header = request.headers.get("Authorization")
#     if not auth_header:
#         raise HTTPException(status_code=401, detail="Missing authorization header")
#     try:
#         scheme, token = auth_header.split(" ")
#         if scheme.lower() != "bearer":
#             raise HTTPException(status_code=401, detail="Invalid authorization scheme")
#     except ValueError:
#         raise HTTPException(status_code=401, detail="Invalid authorization header")
#
#     try:
#         payload = jwt.decode(
#             token,
#             settings.SUPABASE_JWT_SECRET,
#             algorithms=["HS256"],
#             options={"require": ["exp", "sub"]}
#         )
#         auth_user_id = payload["sub"]
#     except jwt.ExpiredSignatureError:
#         raise HTTPException(status_code=401, detail="Token expired")
#     except jwt.InvalidTokenError:
#         raise HTTPException(status_code=401, detail="Invalid token")
#
#     user_data = await db.get_user_by_auth_id(auth_user_id)
#     if not user_data:
#         raise HTTPException(status_code=404, detail="User not found")
#
#     request.state.user_id = user_data["id"]
#     request.state.auth_user_id = auth_user_id
#     request.state.user_data = user_data
#
#     return await call_next(request)


# src/api/middleware/auth.py
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import time
from jose import jwt
from jose.jwk import construct
from src.config import get_settings
from src.services.supabase.database import DatabaseService

settings = get_settings()
db = DatabaseService()
security = HTTPBearer()

# ✅ Correct JWKS endpoint
JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
CACHE_TTL = 3600  # 1 hour
_jwks_cache = None
_jwks_cache_time = 0

async def get_jwk(kid: str):
    """Fetch JWKS from Supabase with the required apikey header."""
    global _jwks_cache, _jwks_cache_time
    now = time.time()

    # Refresh cache if expired or empty
    if _jwks_cache is None or now - _jwks_cache_time > CACHE_TTL:
        async with httpx.AsyncClient() as client:
            # ✅ MUST include the apikey header
            resp = await client.get(
                JWKS_URL,
                headers={"apikey": settings.SUPABASE_ANON_KEY}
            )
            resp.raise_for_status()
            data = resp.json()
            # The JWKS response has a "keys" field
            _jwks_cache = data.get("keys", [])
            _jwks_cache_time = now

    for key in _jwks_cache:
        if key.get("kid") == kid:
            return key

    # Force a fresh fetch if key not found (key rotation)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            JWKS_URL,
            headers={"apikey": settings.SUPABASE_ANON_KEY}
        )
        resp.raise_for_status()
        data = resp.json()
        _jwks_cache = data.get("keys", [])
        _jwks_cache_time = now

    for key in _jwks_cache:
        if key.get("kid") == kid:
            return key

    raise HTTPException(status_code=401, detail="No matching signing key found")

async def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT token using JWKS public keys."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Missing kid")

        jwk = await get_jwk(kid)
        public_key = construct(jwk)

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL}/auth/v1"
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTClaimsError as e:
        raise HTTPException(status_code=401, detail=f"Invalid claims: {e}")
    except Exception as e:
        print(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    payload = await verify_supabase_token(credentials.credentials)
    auth_user_id = payload.get("sub")
    if not auth_user_id:
        raise HTTPException(status_code=401, detail="Missing user ID")

    user_data = await db.get_user_by_auth_id(auth_user_id)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_data["id"],
        "auth_user_id": auth_user_id,
        "user_data": user_data
    }

async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public endpoints (no auth)
    if (path in ["/", "/docs", "/openapi.json", "/redoc"] or
        path.startswith("/docs/") or path.startswith("/redoc/") or
        path.startswith("/api/v1/health") or
        path.startswith("/api/v1/test")):
        return await call_next(request)

    # Development bypass
    if settings.DEBUG and path.startswith("/api/v1/chat"):
        request.state.user_id = "test-device-id"
        request.state.auth_user_id = "test-auth-id"
        request.state.user_data = {"id": "test-device-id", "free_chat_attempts": 3}
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        scheme, token = auth_header.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    payload = await verify_supabase_token(token)
    auth_user_id = payload.get("sub")
    if not auth_user_id:
        raise HTTPException(status_code=401, detail="Missing user ID")

    user_data = await db.get_user_by_auth_id(auth_user_id)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    request.state.user_id = user_data["id"]
    request.state.auth_user_id = auth_user_id
    request.state.user_data = user_data

    return await call_next(request)