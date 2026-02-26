import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id

router = APIRouter(prefix="/auth", tags=["auth"])

# Whitelist of environments where test auth is allowed
ALLOWED_TEST_ENVIRONMENTS = frozenset({"test", "development", "local"})


class TelegramAuthRequest(BaseModel):
    init_data: str


class TestAuthRequest(BaseModel):
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = "Test"
    last_name: Optional[str] = "User"


class TelegramAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    telegram_id: int
    display_name: str


class UserTypeInfo(BaseModel):
    """Response for /auth/me endpoint."""
    user_id: str
    telegram_id: Optional[int]
    user_type: str
    communities_owned: list[dict]
    communities_member: list[dict]


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """
    Validate Telegram Mini App initData using HMAC-SHA-256.
    Returns parsed user data if valid, raises HTTPException if invalid.
    """
    # Parse init_data as URL query string
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))

    if "hash" not in parsed:
        raise HTTPException(status_code=400, detail="Missing hash in init_data")

    received_hash = parsed.pop("hash")

    # Sort and create data-check-string
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # Create secret key: HMAC-SHA256(bot_token, "WebAppData")
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256
    ).digest()

    # Calculate hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid init_data signature")

    # Parse user JSON
    if "user" not in parsed:
        raise HTTPException(status_code=400, detail="Missing user in init_data")

    try:
        user = json.loads(parsed["user"])
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid user JSON")

    return user


@router.post("/telegram", response_model=TelegramAuthResponse)
async def auth_telegram(request: TelegramAuthRequest):
    """
    Authenticate user via Telegram Mini App initData.
    Creates or finds user in Supabase Auth and returns session tokens.
    """
    settings = get_settings()

    # Validate Telegram initData
    telegram_user = validate_telegram_init_data(
        request.init_data,
        settings.telegram_bot_token
    )

    telegram_id = telegram_user["id"]
    username = telegram_user.get("username", "")
    first_name = telegram_user.get("first_name", "User")
    last_name = telegram_user.get("last_name", "")
    display_name = f"{first_name} {last_name}".strip() or f"User {telegram_id}"

    # Create fake email for Supabase Auth
    fake_email = f"tg_{telegram_id}@atlantis.local"
    fake_password = f"tg_auth_{telegram_id}_{settings.telegram_bot_token[:10]}"

    supabase = get_supabase_admin()

    # Try to create user, or get existing
    try:
        # First try to sign in
        auth_response = supabase.auth.sign_in_with_password({
            "email": fake_email,
            "password": fake_password
        })
    except Exception:
        # User doesn't exist, create new one
        try:
            create_response = supabase.auth.admin.create_user({
                "email": fake_email,
                "password": fake_password,
                "email_confirm": True,
                "user_metadata": {
                    "telegram_id": telegram_id,
                    "telegram_username": username,
                    "display_name": display_name
                }
            })
            # Now sign in
            auth_response = supabase.auth.sign_in_with_password({
                "email": fake_email,
                "password": fake_password
            })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create/authenticate user: {str(e)}"
            )

    session = auth_response.session
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return TelegramAuthResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user_id=session.user.id,
        telegram_id=telegram_id,
        display_name=display_name
    )


@router.get("/me", response_model=UserTypeInfo)
async def get_current_user_info(
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get current user info including user type and communities.

    Used by frontend to determine which UI to show.
    """
    from app.services.user_type import get_user_type_info

    user_id = get_user_id(token_payload)

    try:
        info = await get_user_type_info(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user info: {str(e)}")

    print(f"[AUTH /me] user_id={user_id}, user_type={info.user_type.value}, "
          f"communities_owned={len(info.communities_owned)}, "
          f"communities_member={len(info.communities_member)}")

    return UserTypeInfo(
        user_id=info.user_id,
        telegram_id=info.telegram_id,
        user_type=info.user_type.value,
        communities_owned=info.communities_owned,
        communities_member=info.communities_member
    )


@router.post("/telegram/test", response_model=TelegramAuthResponse)
async def auth_telegram_test(
    request: TestAuthRequest,
    x_test_secret: Optional[str] = Header(None, alias="X-Test-Secret")
):
    """
    Test authentication endpoint for automated testing.

    Secured with 3 gates:
    1. Environment whitelist (not production)
    2. test_mode_enabled flag
    3. X-Test-Secret header

    Returns real Supabase session for testing API endpoints.
    """
    settings = get_settings()

    # Gate 1: Environment whitelist
    if settings.environment not in ALLOWED_TEST_ENVIRONMENTS:
        raise HTTPException(status_code=404, detail="Not found")

    # Gate 2: Test mode must be enabled
    if not settings.test_mode_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    # Gate 3: Secret header validation
    if not settings.test_auth_secret or not x_test_secret:
        raise HTTPException(status_code=404, detail="Not found")
    if not hmac.compare_digest(x_test_secret, settings.test_auth_secret):
        raise HTTPException(status_code=404, detail="Not found")

    # Generate test user credentials
    telegram_id = request.telegram_id or 999999999
    username = request.username or "test_user"
    first_name = request.first_name or "Test"
    last_name = request.last_name or "User"
    display_name = f"{first_name} {last_name}".strip()

    # Create fake email for Supabase Auth
    fake_email = f"tg_{telegram_id}@atlantis.local"
    fake_password = f"tg_auth_{telegram_id}_{settings.telegram_bot_token[:10]}"

    supabase = get_supabase_admin()

    # Try to sign in or create user
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": fake_email,
            "password": fake_password
        })
    except Exception:
        try:
            supabase.auth.admin.create_user({
                "email": fake_email,
                "password": fake_password,
                "email_confirm": True,
                "user_metadata": {
                    "telegram_id": telegram_id,
                    "telegram_username": username,
                    "display_name": display_name,
                    "is_test_user": True
                }
            })
            auth_response = supabase.auth.sign_in_with_password({
                "email": fake_email,
                "password": fake_password
            })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create/authenticate test user: {str(e)}"
            )

    session = auth_response.session
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return TelegramAuthResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user_id=session.user.id,
        telegram_id=telegram_id,
        display_name=display_name
    )
