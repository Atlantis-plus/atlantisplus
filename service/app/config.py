from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    supabase_jwt_secret: str

    # OpenAI
    openai_api_key: str

    # Anthropic (Claude)
    anthropic_api_key: str = ""  # Optional: for Claude agent

    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str = ""  # Optional: for webhook verification
    mini_app_url: str = "https://atlantisplus.pages.dev"  # Cloudflare Pages URL

    # Environment
    environment: str = "development"

    # People Data Labs (enrichment)
    pdl_api_key: str = ""
    pdl_monthly_limit: int = 100
    pdl_daily_limit: int = 5

    # Proactive questions
    questions_max_per_day: int = 3
    questions_cooldown_hours: int = 1
    questions_pause_days_after_dismisses: int = 7
    questions_max_consecutive_dismisses: int = 3

    # Test mode (for automated testing)
    test_mode_enabled: bool = False
    test_auth_secret: str = ""

    # Shared database mode (search across ALL users' data)
    # WARNING: For development/testing only! Bypasses owner isolation.
    shared_database_mode: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
