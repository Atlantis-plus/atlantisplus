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
    Send message with inline keyboard buttons that open Mini App for each person.

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

    # Build web_app buttons for each person (limit to max_buttons)
    buttons = []
    for person in people[:max_buttons]:
        person_id = person.get('person_id', '')
        name = person.get('name', 'Unknown')
        # Truncate name if too long for button
        if len(name) > 30:
            name = name[:27] + "..."

        # Mini App URL with startapp parameter for deep linking
        web_app_url = f"https://evgenyq.github.io/atlantisplus/?startapp=person_{person_id}"

        buttons.append([{
            "text": f"👤 {name}",
            "web_app": {"url": web_app_url}
        }])

    # Add "Open Catalog" button at the end if there are results
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


async def send_message_with_dig_deeper(
    chat_id: int,
    text: str,
    people: list[dict],
    original_query: str,
    parse_mode: Optional[str] = None,
    max_buttons: int = 5
) -> dict:
    """
    Send search results with person buttons AND "Dig deeper" button.

    PROGRESSIVE ENHANCEMENT UX:
    ===========================
    This implements the two-tier search UX:

    Tier 1 (just completed): Fast search returned results
    - Show person buttons (open Mini App for each person)
    - Show "Dig deeper" button at the bottom

    When user clicks "Dig deeper":
    - Callback triggers chat_dig_deeper()
    - Claude agent runs with initial results as context
    - Finds non-obvious matches, name variations, etc.

    The original_query is stored in callback_data for Tier 2.
    Since callback_data is limited to 64 bytes and queries can be long,
    we use a hash to store/retrieve the full query.

    Args:
        chat_id: Telegram chat ID
        text: Search results message
        people: List of found people [{person_id, name}]
        original_query: The user's original query (for dig deeper)
        parse_mode: HTML or Markdown
        max_buttons: Max person buttons to show

    Returns:
        Response dict with message_id
    """
    settings = get_settings()

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    # Build web_app buttons for each person
    buttons = []
    for person in people[:max_buttons]:
        person_id = person.get('person_id', '')
        name = person.get('name', 'Unknown')
        if len(name) > 30:
            name = name[:27] + "..."

        web_app_url = f"https://evgenyq.github.io/atlantisplus/?startapp=person_{person_id}"
        buttons.append([{
            "text": f"👤 {name}",
            "web_app": {"url": web_app_url}
        }])

    # Add "Open Catalog" button
    if people:
        buttons.append([{
            "text": "📋 Open Full Catalog",
            "web_app": {"url": "https://evgenyq.github.io/atlantisplus/"}
        }])

    # Add "Dig deeper" button with callback
    # Store query hash → use context system or simple encoding
    # For now, use short hash + store full query in pending_queries
    import hashlib
    query_hash = hashlib.sha256(original_query.encode()).hexdigest()[:12]

    # Store in module-level pending queries (imported from handlers)
    from . import handlers
    handlers.PENDING_DIG_DEEPER_QUERIES[query_hash] = original_query

    buttons.append([{
        "text": "🔍 Dig deeper with AI agent",
        "callback_data": f"dig:{query_hash}"
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
