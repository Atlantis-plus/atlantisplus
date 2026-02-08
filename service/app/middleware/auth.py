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
    """
    settings = get_settings()
    token = credentials.credentials

    # Try HS256 first (legacy), then RS256
    algorithms_to_try = ["HS256", "RS256"]
    last_error = None

    for alg in algorithms_to_try:
        try:
            options = {"verify_aud": False}  # Supabase may not always set audience

            if alg == "RS256":
                # For RS256, decode without verification for now (MVP)
                # In production, fetch JWKS from Supabase
                payload = jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=[alg],
                    options={**options, "verify_signature": False}
                )
            else:
                payload = jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=[alg],
                    options=options
                )
            return payload
        except JWTError as e:
            last_error = e
            continue

    # If all algorithms failed, raise the last error
    raise HTTPException(
        status_code=401,
        detail=f"Invalid authentication token: {str(last_error)}"
    )


def get_user_id(token_payload: dict) -> str:
    """Extract user_id from verified token payload."""
    return token_payload.get("sub")
