"""
User Type Resolution Service.

Determines user type for proper routing and access control:
- ATLANTIS_PLUS: Full access power-connectors
- COMMUNITY_ADMIN: Channel owners who created communities
- COMMUNITY_MEMBER: Participants who joined via invite link
- NEW_USER: Unknown user, show welcome
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass

from app.supabase_client import get_supabase_admin


class UserType(str, Enum):
    """User type enum for routing decisions."""
    ATLANTIS_PLUS = "atlantis_plus"
    COMMUNITY_ADMIN = "community_admin"
    COMMUNITY_MEMBER = "community_member"
    NEW_USER = "new_user"


@dataclass
class UserTypeInfo:
    """Full user type information with related data."""
    user_type: UserType
    user_id: Optional[str] = None
    telegram_id: Optional[int] = None
    communities_owned: list[dict] = None
    communities_member: list[dict] = None

    def __post_init__(self):
        if self.communities_owned is None:
            self.communities_owned = []
        if self.communities_member is None:
            self.communities_member = []


def get_user_type_by_user_id(user_id: str) -> UserType:
    """
    Determine user type by Supabase user_id.

    Priority:
    1. Is Atlantis+ member? → ATLANTIS_PLUS
    2. Owns any community? → COMMUNITY_ADMIN
    3. Is member of any community? → COMMUNITY_MEMBER
    4. Otherwise → NEW_USER

    Args:
        user_id: Supabase auth user ID

    Returns:
        UserType enum value
    """
    supabase = get_supabase_admin()

    # 1. Check Atlantis+ membership
    try:
        result = supabase.table("atlantis_plus_member").select(
            "user_id"
        ).eq("user_id", user_id).execute()

        if result.data:
            return UserType.ATLANTIS_PLUS
    except Exception:
        pass  # Table might not exist yet

    # 2. Check if user owns any community
    try:
        result = supabase.table("community").select(
            "community_id"
        ).eq("owner_id", user_id).eq("is_active", True).limit(1).execute()

        if result.data:
            return UserType.COMMUNITY_ADMIN
    except Exception:
        pass

    # 3. Check if user is member of any community (via person.telegram_id)
    # We need telegram_id for this, which we get from auth user metadata
    try:
        # Get user metadata to find telegram_id
        user = supabase.auth.admin.get_user_by_id(user_id)
        telegram_id = user.user.user_metadata.get("telegram_id")

        if telegram_id:
            result = supabase.table("person").select(
                "person_id"
            ).eq("telegram_id", telegram_id).not_.is_("community_id", "null").eq(
                "status", "active"
            ).limit(1).execute()

            if result.data:
                return UserType.COMMUNITY_MEMBER
    except Exception:
        pass

    return UserType.NEW_USER


def get_user_type_by_telegram_id(telegram_id: int) -> UserType:
    """
    Determine user type by Telegram ID.

    Used in bot handlers before we have Supabase user_id.

    Args:
        telegram_id: Telegram user ID

    Returns:
        UserType enum value
    """
    supabase = get_supabase_admin()

    # First, find Supabase user by telegram_id
    try:
        users = supabase.auth.admin.list_users()
        user_id = None

        for user in users:
            user_metadata = getattr(user, 'user_metadata', {}) or {}
            if user_metadata.get("telegram_id") == telegram_id:
                user_id = str(user.id)
                break

        if user_id:
            return get_user_type_by_user_id(user_id)
    except Exception:
        pass

    # If user doesn't exist in Supabase, check if they're a community member
    # (they might have filled profile before creating account)
    try:
        result = supabase.table("person").select(
            "person_id"
        ).eq("telegram_id", telegram_id).not_.is_("community_id", "null").eq(
            "status", "active"
        ).limit(1).execute()

        if result.data:
            return UserType.COMMUNITY_MEMBER
    except Exception:
        pass

    return UserType.NEW_USER


async def get_user_type_info(user_id: str, telegram_id: Optional[int] = None) -> UserTypeInfo:
    """
    Get full user type information including related communities.

    Args:
        user_id: Supabase auth user ID
        telegram_id: Optional Telegram ID (for member lookup)

    Returns:
        UserTypeInfo with user_type and community lists
    """
    supabase = get_supabase_admin()

    # Get telegram_id if not provided
    if not telegram_id:
        try:
            user = supabase.auth.admin.get_user_by_id(user_id)
            telegram_id = user.user.user_metadata.get("telegram_id")
        except Exception:
            pass

    user_type = get_user_type_by_user_id(user_id)
    communities_owned = []
    communities_member = []

    # Get owned communities (for ATLANTIS_PLUS and COMMUNITY_ADMIN)
    if user_type in [UserType.ATLANTIS_PLUS, UserType.COMMUNITY_ADMIN]:
        try:
            result = supabase.table("community").select(
                "community_id, name, invite_code, is_active, created_at"
            ).eq("owner_id", user_id).eq("is_active", True).execute()

            communities_owned = result.data or []
        except Exception:
            pass

    # Get member communities (for COMMUNITY_MEMBER, but also useful for others)
    if telegram_id:
        try:
            result = supabase.table("person").select(
                "person_id, community_id, created_at, community:community_id(name, community_id)"
            ).eq("telegram_id", telegram_id).not_.is_("community_id", "null").eq(
                "status", "active"
            ).execute()

            for row in result.data or []:
                if row.get("community"):
                    communities_member.append({
                        "community_id": row["community"]["community_id"],
                        "name": row["community"]["name"],
                        "person_id": row["person_id"],
                        "created_at": row["created_at"]
                    })
        except Exception:
            pass

    return UserTypeInfo(
        user_type=user_type,
        user_id=user_id,
        telegram_id=telegram_id,
        communities_owned=communities_owned,
        communities_member=communities_member
    )


def is_atlantis_plus_member(user_id: str) -> bool:
    """Check if user is Atlantis+ member."""
    return get_user_type_by_user_id(user_id) == UserType.ATLANTIS_PLUS


def can_create_community(user_id: str) -> bool:
    """Check if user can create communities (Atlantis+ members only for now)."""
    return is_atlantis_plus_member(user_id)


def get_community_by_invite_code(invite_code: str) -> Optional[dict]:
    """
    Get community info by invite code.

    Args:
        invite_code: 12-character invite code

    Returns:
        Community dict or None if not found/inactive
    """
    supabase = get_supabase_admin()

    try:
        result = supabase.table("community").select(
            "community_id, owner_id, name, description, invite_code, settings, is_active"
        ).eq("invite_code", invite_code).eq("is_active", True).single().execute()

        return result.data
    except Exception:
        return None
