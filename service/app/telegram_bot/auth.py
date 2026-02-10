from __future__ import annotations

"""
Authentication bridge between Telegram and Supabase.

Maps telegram_id to Supabase user and generates access tokens.
"""

from typing import Dict, Any
from app.supabase_client import get_supabase_admin
from .logging_config import bot_logger as logger


async def get_or_create_user(telegram_id: str, telegram_username: str | None = None, display_name: str | None = None) -> Dict[str, Any]:
    """
    Find or create Supabase user by telegram_id.
    Returns user info with access_token for API calls.
    """
    logger.info(f"Authenticating telegram_id={telegram_id}, username={telegram_username}, display_name={display_name}")

    supabase = get_supabase_admin()
    fake_email = f"tg_{telegram_id}@atlantis.local"

    # 1. Try to find existing user by telegram_id or email
    try:
        users_response = supabase.auth.admin.list_users()
        logger.debug(f"Found {len(users_response)} total users in system")

        for user in users_response:
            user_metadata = getattr(user, 'user_metadata', {}) or {}
            user_email = getattr(user, 'email', '')

            # Match by telegram_id in metadata OR by email pattern
            if user_metadata.get("telegram_id") == telegram_id or user_email == fake_email:
                logger.info(f"Found existing user: user_id={user.id}, email={user_email}")

                # Update metadata with telegram_id if missing
                if not user_metadata.get("telegram_id"):
                    logger.info(f"Updating telegram_id in metadata for user_id={user.id}")
                    try:
                        supabase.auth.admin.update_user_by_id(
                            str(user.id),
                            {"user_metadata": {**user_metadata, "telegram_id": telegram_id}}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update metadata: {e}")

                # Generate access token
                link_response = supabase.auth.admin.generate_link({
                    "type": "magiclink",
                    "email": user_email
                })

                # Debug: log the structure
                logger.debug(f"link_response type: {type(link_response)}")
                logger.debug(f"link_response attributes: {dir(link_response)}")
                if hasattr(link_response, 'properties'):
                    logger.debug(f"properties type: {type(link_response.properties)}")
                    logger.debug(f"properties attributes: {dir(link_response.properties)}")
                    logger.debug(f"properties dict: {vars(link_response.properties) if hasattr(link_response.properties, '__dict__') else 'no __dict__'}")

                # For internal API calls, use service_role_key
                # This bypasses RLS but we're on the server anyway
                from app.config import get_settings
                settings = get_settings()
                access_token = settings.supabase_service_role_key
                logger.info(f"Using service_role_key for internal API calls")

                return {
                    "user_id": str(user.id),
                    "telegram_id": telegram_id,
                    "access_token": access_token,
                    "display_name": user_metadata.get("display_name", display_name or f"User {telegram_id}")
                }

    except Exception as e:
        logger.error(f"Error searching for existing user: {e}", exc_info=True)
        raise

    # 2. User not found - create new user
    logger.info(f"User not found, creating new user with email={fake_email}")

    user_metadata = {
        "telegram_id": telegram_id,
        "display_name": display_name or telegram_username or f"User {telegram_id}"
    }

    if telegram_username:
        user_metadata["telegram_username"] = telegram_username

    try:
        # Create user
        new_user = supabase.auth.admin.create_user({
            "email": fake_email,
            "email_confirm": True,
            "user_metadata": user_metadata
        })

        logger.info(f"Created new user: user_id={new_user.user.id}")

        # For internal API calls, use service_role_key
        from app.config import get_settings
        settings = get_settings()
        access_token = settings.supabase_service_role_key
        logger.info(f"Using service_role_key for internal API calls")

        return {
            "user_id": str(new_user.user.id),
            "telegram_id": telegram_id,
            "access_token": access_token,
            "display_name": user_metadata["display_name"]
        }

    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        raise Exception(f"Failed to create user for telegram_id {telegram_id}: {str(e)}")
