from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from app.config import get_settings

security = HTTPBearer()


async def verify_supabase_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Validate Supabase JWT from Authorization header.
    Returns the decoded token payload with user info.

    Security: Only HS256 algorithm is supported. RS256 requires JWKS
    verification which is not implemented, so we reject it to prevent
    signature bypass attacks.
    """
    settings = get_settings()
    token = credentials.credentials

    alg = "unknown"
    try:
        # Log the algorithm being used
        unverified = jwt.get_unverified_header(token)
        alg = unverified.get("alg", "unknown")
        print(f"[AUTH] Token algorithm: {alg}")

        # Accept HS256 (standard Supabase) - verify with JWT secret
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
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
