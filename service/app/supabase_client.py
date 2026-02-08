from supabase import create_client, Client
from app.config import get_settings


def get_supabase_admin() -> Client:
    """Service role client — bypasses RLS, for server-side operations."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key
    )


def get_supabase_anon() -> Client:
    """Anon client — respects RLS, for testing."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key
    )
