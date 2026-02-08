import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.supabase_client import get_supabase_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: str


class TelegramAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    telegram_id: int
    display_name: str


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
