"""
Main Telegram bot handler.

Uses python-telegram-bot library with webhook mode.
"""

import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from app.config import get_settings
from .logging_config import bot_logger as logger
from .handlers import (
    handle_start_command,
    handle_help_command,
    handle_reset_command,
    handle_text_message,
    handle_voice_message,
    handle_callback_query,
    handle_error,
)


# Global application instance (initialized once)
_application: Application | None = None


def get_bot_application() -> Application:
    """Get or create telegram bot application."""
    global _application

    if _application is None:
        settings = get_settings()

        # Create application
        _application = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Register handlers
        _application.add_handler(CommandHandler("start", handle_start_command))
        _application.add_handler(CommandHandler("help", handle_help_command))
        _application.add_handler(CommandHandler("reset", handle_reset_command))

        # Text messages
        _application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        )

        # Voice messages
        _application.add_handler(
            MessageHandler(filters.VOICE, handle_voice_message)
        )

        # Callback queries (inline keyboard buttons)
        _application.add_handler(
            CallbackQueryHandler(handle_callback_query)
        )

        # Error handler
        _application.add_error_handler(handle_error)

        logger.info("Telegram bot application initialized")

    return _application


async def handle_telegram_update(update_data: dict) -> None:
    """
    Process incoming webhook update from Telegram.

    This is called by FastAPI webhook endpoint.
    Runs handlers in background (fire-and-forget).
    """
    try:
        app = get_bot_application()

        # Convert dict to Update object
        update = Update.de_json(update_data, app.bot)

        if update:
            # Process update through handlers
            await app.process_update(update)
        else:
            logger.warning("Received invalid update data")

    except Exception as e:
        logger.error(f"Failed to process update: {e}", exc_info=True)


async def initialize_bot() -> None:
    """
    Initialize bot application (call on startup).
    """
    app = get_bot_application()
    await app.initialize()
    logger.info("Bot initialized successfully")


async def shutdown_bot() -> None:
    """
    Shutdown bot application (call on shutdown).
    """
    global _application
    if _application:
        await _application.shutdown()
        logger.info("Bot shut down")
