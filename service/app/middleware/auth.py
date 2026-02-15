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

    try:
        # Only allow HS256 - RS256 would require JWKS verification
        # Rejecting RS256 prevents signature bypass attacks
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],  # Explicitly only HS256
            options={"verify_aud": False}  # Supabase may not always set audience
        )
        return payload
    except JWTError as e:
        # Don't expose internal error details
        print(f"[AUTH] JWT verification failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token"
        )


def get_user_id(token_payload: dict) -> str:
    """Extract user_id from verified token payload."""
    return token_payload.get("sub")
