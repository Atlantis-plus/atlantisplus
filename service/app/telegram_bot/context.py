from __future__ import annotations

"""
Dialog context storage for Telegram bot.

For MVP: simple in-memory dict.
For production: migrate to Redis or Supabase table.
"""

from typing import Dict, Any

# In-memory storage: telegram_user_id -> context dict
_context_storage: Dict[str, Dict[str, Any]] = {}


async def load_context(user_id: str) -> Dict[str, Any]:
    """Load dialog context for user."""
    return _context_storage.get(user_id, {})


async def save_context(user_id: str, data: Dict[str, Any]) -> None:
    """Save dialog context for user (merge with existing)."""
    _context_storage[user_id] = {
        **_context_storage.get(user_id, {}),
        **data
    }


async def clear_context(user_id: str) -> None:
    """Clear dialog context for user."""
    _context_storage.pop(user_id, None)


async def get_active_session(user_id: str) -> str | None:
    """Get active chat session ID for user."""
    context = _context_storage.get(user_id, {})
    return context.get("chat_session_id")


async def set_active_session(user_id: str, session_id: str | None) -> None:
    """Set active chat session ID for user."""
    if user_id not in _context_storage:
        _context_storage[user_id] = {}
    _context_storage[user_id]["chat_session_id"] = session_id
