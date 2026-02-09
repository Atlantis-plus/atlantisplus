"""
Telegram Bot module for Atlantis Plus.

ARCHITECTURE: Thin routing layer - NO business logic duplication!
- Receives webhook from Telegram
- Authenticates user (telegram_id → Supabase)
- Classifies message via dispatcher
- Routes to existing endpoints (POST /chat, POST /process/text)
- Returns response to Telegram

All business logic stays in existing endpoints:
- /process/text - extraction pipeline
- /process/voice - Whisper + extraction
- /chat - chat agent with tool use
"""

from .bot import handle_telegram_update
from .auth import get_or_create_user
from .context import load_context, save_context, clear_context
from .api_client import get_api_client

__all__ = [
    "handle_telegram_update",
    "get_or_create_user",
    "load_context",
    "save_context",
    "clear_context",
    "get_api_client",
]
