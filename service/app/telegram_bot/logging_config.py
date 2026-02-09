"""
Logging configuration for Telegram bot.
"""

import logging
import sys

def setup_logging():
    """Setup logging with proper format and handlers."""

    # Create logger
    logger = logging.getLogger("telegram_bot")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler with formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger

# Global logger instance
bot_logger = setup_logging()
