"""
Telegram Bot API client for sending messages.

Simple wrapper for sending messages back to Telegram.
"""

import httpx
from typing import Optional

from app.config import get_settings


async def send_message(chat_id: int, text: str, parse_mode: Optional[str] = None) -> None:
    """
    Send message to Telegram user.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        parse_mode: Optional parse mode (Markdown, HTML)
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()


async def send_chat_action(chat_id: int, action: str = "typing") -> None:
    """
    Send chat action (typing indicator).

    Args:
        chat_id: Telegram chat ID
        action: Action type (typing, upload_voice, etc.)
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendChatAction"

    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "action": action})


async def send_message_with_buttons(
    chat_id: int,
    text: str,
    buttons: list[list[dict]],
    parse_mode: Optional[str] = None
) -> dict:
    """
    Send message with inline keyboard buttons.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        buttons: 2D array of button dicts, each with 'text' and 'callback_data'
                 Example: [[{"text": "Yes", "callback_data": "merge_yes"}]]
        parse_mode: Optional parse mode (Markdown, HTML)

    Returns:
        Response dict with message_id
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def edit_message_text(
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: Optional[str] = None
) -> None:
    """
    Edit an existing message.

    Args:
        chat_id: Telegram chat ID
        message_id: ID of message to edit
        text: New message text
        parse_mode: Optional parse mode
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageText"

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()


async def send_message_with_web_app_buttons(
    chat_id: int,
    text: str,
    people: list[dict],
    parse_mode: Optional[str] = None,
    max_buttons: int = 5
) -> dict:
    """
    Send message with inline keyboard buttons for people.

    Uses callback_data buttons (not web_app) so clicking doesn't create
    new Mini App instances. Instead, sends Realtime event to navigate
    within the already-open Mini App.

    Args:
        chat_id: Telegram chat ID
        text: Message text
        people: List of dicts with 'person_id' and 'name' keys
        parse_mode: Optional parse mode (Markdown, HTML)
        max_buttons: Maximum number of buttons to show (default 5)

    Returns:
        Response dict with message_id
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    # Build callback_data buttons for each person (limit to max_buttons)
    buttons = []
    for person in people[:max_buttons]:
        person_id = person.get('person_id', '')
        name = person.get('name', 'Unknown')
        # Truncate name if too long for button
        if len(name) > 30:
            name = name[:27] + "..."

        # Use callback_data to navigate within existing Mini App
        buttons.append([{
            "text": f"👤 {name}",
            "callback_data": f"view_person:{person_id}"
        }])

    # Add "Open Catalog" button at the end - this one uses web_app
    # as it's for when user doesn't have app open yet
    if people:
        buttons.append([{
            "text": "📋 Open Full Catalog",
            "web_app": {"url": "https://evgenyq.github.io/atlantisplus/"}
        }])

    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }

    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def broadcast_navigation(user_id: str, person_id: str) -> bool:
    """
    Broadcast navigation event to user's Mini App via Supabase Realtime.

    The Mini App subscribes to a channel named 'navigation:{telegram_id}'
    and receives events to navigate to specific people.

    Args:
        user_id: Supabase user UUID
        person_id: Person UUID to navigate to

    Returns:
        True if broadcast succeeded
    """
    from app.supabase_client import get_supabase_admin

    supabase = get_supabase_admin()

    try:
        # Get telegram_id from user metadata
        users_response = supabase.auth.admin.list_users()

        telegram_id = None
        for user in users_response:
            if str(user.id) == user_id:
                user_metadata = getattr(user, 'user_metadata', {}) or {}
                telegram_id = user_metadata.get("telegram_id")
                break

        if not telegram_id:
            return False

        # Broadcast via Realtime using postgres_changes channel
        # The Mini App will subscribe to this channel
        channel_name = f"navigation:{telegram_id}"

        # Use Supabase's broadcast feature
        # Note: supabase-py doesn't have direct broadcast support,
        # so we use a workaround with a navigation_events table
        supabase.table("navigation_events").insert({
            "telegram_id": str(telegram_id),
            "person_id": person_id,
            "event_type": "navigate_person"
        }).execute()

        return True

    except Exception as e:
        import logging
        logging.error(f"Broadcast navigation failed: {e}")
        return False


async def get_telegram_id_for_user(user_id: str) -> Optional[int]:
    """
    Get Telegram chat ID from Supabase user_id.

    Returns:
        Telegram ID (int) or None if not found
    """
    from app.supabase_client import get_supabase_admin

    supabase = get_supabase_admin()

    try:
        users_response = supabase.auth.admin.list_users()

        for user in users_response:
            if str(user.id) == user_id:
                user_metadata = getattr(user, 'user_metadata', {}) or {}
                telegram_id = user_metadata.get("telegram_id")
                if telegram_id:
                    return int(telegram_id)

        return None

    except Exception:
        return None
