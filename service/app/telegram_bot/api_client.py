"""
Internal API client for calling existing endpoints.

This module provides a thin wrapper to call our own API endpoints
from the Telegram bot handlers.
"""

import httpx
from typing import Optional, Dict, Any

from app.config import get_settings


class InternalAPIClient:
    """
    Client for calling our own API endpoints from Telegram bot.

    Uses internal base URL (localhost for same process calls).
    """

    def __init__(self, base_url: str = None):
        # Use Railway public domain for internal calls
        # In same process, can call via external URL (Railway handles routing)
        settings = get_settings()
        self.base_url = base_url or "https://atlantisplus-production.up.railway.app"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def process_text(self, text: str, access_token: str) -> Dict[str, Any]:
        """
        Call POST /process/text endpoint.

        Uses existing extraction pipeline - NO duplication of logic.
        """
        response = await self.client.post(
            f"{self.base_url}/process/text",
            json={"text": text},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def process_voice(self, storage_path: str, access_token: str) -> Dict[str, Any]:
        """
        Call POST /process/voice endpoint.

        Uses existing Whisper + extraction pipeline - NO duplication.
        """
        response = await self.client.post(
            f"{self.base_url}/process/voice",
            json={"storage_path": storage_path},
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def chat(self, message: str, session_id: Optional[str], access_token: str) -> Dict[str, Any]:
        """
        Call POST /chat endpoint.

        Uses existing chat agent with tool use - NO duplication.
        """
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id

        response = await self.client.post(
            f"{self.base_url}/chat",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def get_processing_status(self, evidence_id: str, access_token: str) -> Dict[str, Any]:
        """
        Call GET /process/status/{evidence_id} endpoint.

        Poll for extraction completion.
        """
        response = await self.client.get(
            f"{self.base_url}/process/status/{evidence_id}",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


# Global instance
_api_client: Optional[InternalAPIClient] = None


def get_api_client() -> InternalAPIClient:
    """Get or create internal API client singleton."""
    global _api_client
    if _api_client is None:
        _api_client = InternalAPIClient()
    return _api_client
