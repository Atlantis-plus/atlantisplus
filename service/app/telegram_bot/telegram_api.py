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
