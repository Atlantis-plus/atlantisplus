from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from jose.backends import ECKey
import httpx
from functools import lru_cache
from app.config import get_settings

security = HTTPBearer()

# Cache JWKS for 10 minutes
_jwks_cache = {"keys": None, "fetched_at": 0}
JWKS_CACHE_SECONDS = 600


async def _get_jwks():
    """Fetch JWKS from Supabase, with caching."""
    import time

    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_SECONDS:
        return _jwks_cache["keys"]

    settings = get_settings()
    # Extract project ID from URL: https://xxx.supabase.co -> xxx
    project_id = settings.supabase_url.replace("https://", "").split(".")[0]
    jwks_url = f"https://{project_id}.supabase.co/auth/v1/.well-known/jwks.json"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            jwks = response.json()
            _jwks_cache["keys"] = jwks.get("keys", [])
            _jwks_cache["fetched_at"] = now
            print(f"[AUTH] Fetched JWKS with {len(_jwks_cache['keys'])} keys")
            return _jwks_cache["keys"]
    except Exception as e:
        print(f"[AUTH] Failed to fetch JWKS: {e}")
        # Return cached keys if available, even if stale
        if _jwks_cache["keys"]:
            return _jwks_cache["keys"]
        return []


def _find_key_by_kid(keys: list, kid: str) -> dict | None:
    """Find JWK by key ID."""
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


async def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Validate Supabase JWT from Authorization header.

    Supports both HS256 (legacy) and ES256 (new default since Oct 2025).
    ES256 tokens are verified using JWKS from Supabase.
    """
    settings = get_settings()
    token = credentials.credentials

    alg = "unknown"
    kid = None
    try:
        # Get header to determine algorithm
        unverified = jwt.get_unverified_header(token)
        alg = unverified.get("alg", "unknown")
        kid = unverified.get("kid")
        print(f"[AUTH] Token algorithm: {alg}, kid: {kid}")

        if alg == "HS256":
            # Legacy symmetric verification
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
        elif alg == "ES256":
            # Asymmetric verification via JWKS
            jwks = await _get_jwks()

            if not jwks:
                raise JWTError("Could not fetch JWKS for ES256 verification")

            # Find the key matching the token's kid
            jwk = _find_key_by_kid(jwks, kid) if kid else jwks[0] if jwks else None

            if not jwk:
                raise JWTError(f"No matching key found for kid={kid}")

            # Verify with the public key
            payload = jwt.decode(
                token,
                jwk,
                algorithms=["ES256"],
                options={"verify_aud": False}
            )
        else:
            raise JWTError(f"Unsupported algorithm: {alg}")

        print(f"[AUTH] Token verified successfully for user: {payload.get('sub', 'unknown')}")
        return payload
    except JWTError as e:
        print(f"[AUTH] JWT verification failed: {e}, algorithm was: {alg}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token"
        )


def get_user_id(token_payload: dict) -> str:
    """Extract user_id from verified token payload."""
    return token_payload.get("sub")
