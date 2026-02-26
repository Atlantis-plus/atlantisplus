"""
Community API.

Endpoints for managing communities (channel owner intake mode).
"""

from typing import Optional, List
from uuid import UUID
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.user_type import UserType, get_user_type_by_user_id, can_create_community

router = APIRouter(prefix="/communities", tags=["communities"])


# ============================================
# Request/Response Models
# ============================================

class CreateCommunityRequest(BaseModel):
    name: str
    description: Optional[str] = None
    telegram_channel_id: Optional[int] = None


class UpdateCommunityRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    telegram_channel_id: Optional[int] = None
    settings: Optional[dict] = None


class CommunityResponse(BaseModel):
    community_id: str
    name: str
    description: Optional[str]
    invite_code: str
    telegram_channel_id: Optional[int]
    is_active: bool
    created_at: str
    updated_at: str
    member_count: int = 0


class CommunityPublicInfo(BaseModel):
    """Public info shown during join flow."""
    community_id: str
    name: str
    description: Optional[str]


class InviteCodeResponse(BaseModel):
    invite_code: str
    invite_url: str


class CommunityMember(BaseModel):
    person_id: str
    display_name: str
    telegram_id: Optional[int]
    created_at: str


# ============================================
# Endpoints
# ============================================

@router.post("", response_model=CommunityResponse)
async def create_community(
    req: CreateCommunityRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Create a new community.

    Only Atlantis+ members can create communities.
    Returns the community with its invite code.
    """
    user_id = get_user_id(token_payload)

    # Check permission
    if not can_create_community(user_id):
        raise HTTPException(
            status_code=403,
            detail="Only Atlantis+ members can create communities"
        )

    supabase = get_supabase_admin()

    # Create community
    result = supabase.table("community").insert({
        "owner_id": user_id,
        "name": req.name,
        "description": req.description,
        "telegram_channel_id": req.telegram_channel_id,
        "settings": {},
        "is_active": True
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create community")

    community = result.data[0]

    return CommunityResponse(
        community_id=community["community_id"],
        name=community["name"],
        description=community.get("description"),
        invite_code=community["invite_code"],
        telegram_channel_id=community.get("telegram_channel_id"),
        is_active=community["is_active"],
        created_at=community["created_at"],
        updated_at=community["updated_at"],
        member_count=0
    )


@router.get("", response_model=List[CommunityResponse])
async def list_my_communities(
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    List communities owned by current user.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get owned communities
    result = supabase.table("community").select(
        "community_id, name, description, invite_code, telegram_channel_id, is_active, created_at, updated_at"
    ).eq("owner_id", user_id).order("created_at", desc=True).execute()

    communities = []
    for c in result.data or []:
        # Get member count
        count_result = supabase.table("person").select(
            "person_id", count="exact"
        ).eq("community_id", c["community_id"]).eq("status", "active").execute()

        member_count = count_result.count or 0

        communities.append(CommunityResponse(
            community_id=c["community_id"],
            name=c["name"],
            description=c.get("description"),
            invite_code=c["invite_code"],
            telegram_channel_id=c.get("telegram_channel_id"),
            is_active=c["is_active"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            member_count=member_count
        ))

    return communities


@router.get("/by-invite/{invite_code}", response_model=CommunityPublicInfo)
async def get_community_by_invite(invite_code: str):
    """
    Get public community info by invite code.

    Used in join flow - no auth required.
    """
    supabase = get_supabase_admin()

    try:
        result = supabase.table("community").select(
            "community_id, name, description"
        ).eq("invite_code", invite_code).eq("is_active", True).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Community not found")

    return CommunityPublicInfo(
        community_id=result.data["community_id"],
        name=result.data["name"],
        description=result.data.get("description")
    )


@router.get("/{community_id}", response_model=CommunityResponse)
async def get_community(
    community_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get community details.

    Only owner can see full details.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    try:
        result = supabase.table("community").select(
            "community_id, owner_id, name, description, invite_code, telegram_channel_id, is_active, created_at, updated_at"
        ).eq("community_id", community_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Community not found")

    community = result.data

    # Check ownership
    if community["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get member count
    count_result = supabase.table("person").select(
        "person_id", count="exact"
    ).eq("community_id", community_id).eq("status", "active").execute()

    return CommunityResponse(
        community_id=community["community_id"],
        name=community["name"],
        description=community.get("description"),
        invite_code=community["invite_code"],
        telegram_channel_id=community.get("telegram_channel_id"),
        is_active=community["is_active"],
        created_at=community["created_at"],
        updated_at=community["updated_at"],
        member_count=count_result.count or 0
    )


@router.put("/{community_id}", response_model=CommunityResponse)
async def update_community(
    community_id: str,
    req: UpdateCommunityRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Update community settings.

    Only owner can update.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Check ownership
    try:
        check = supabase.table("community").select(
            "owner_id"
        ).eq("community_id", community_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not check.data or check.data["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Build update data
    update_data = {}
    if req.name is not None:
        update_data["name"] = req.name
    if req.description is not None:
        update_data["description"] = req.description
    if req.telegram_channel_id is not None:
        update_data["telegram_channel_id"] = req.telegram_channel_id
    if req.settings is not None:
        update_data["settings"] = req.settings

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update
    result = supabase.table("community").update(
        update_data
    ).eq("community_id", community_id).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Update failed")

    # Return updated community
    return await get_community(community_id, token_payload)


@router.post("/{community_id}/regenerate-invite", response_model=InviteCodeResponse)
async def regenerate_invite_code(
    community_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Generate new invite code for community.

    Old code becomes invalid immediately.
    Only owner can regenerate.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Check ownership
    try:
        check = supabase.table("community").select(
            "owner_id"
        ).eq("community_id", community_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not check.data or check.data["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Generate new code
    new_code = secrets.token_hex(6)

    result = supabase.table("community").update({
        "invite_code": new_code
    }).eq("community_id", community_id).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to regenerate code")

    return InviteCodeResponse(
        invite_code=new_code,
        invite_url=f"https://t.me/atlantisplus_bot?start=join_{new_code}"
    )


@router.get("/{community_id}/members", response_model=List[CommunityMember])
async def list_community_members(
    community_id: str,
    limit: int = 100,
    offset: int = 0,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    List members of a community.

    Only owner can see members.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Check ownership
    try:
        check = supabase.table("community").select(
            "owner_id"
        ).eq("community_id", community_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not check.data or check.data["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get members
    result = supabase.table("person").select(
        "person_id, display_name, telegram_id, created_at"
    ).eq("community_id", community_id).eq("status", "active").order(
        "created_at", desc=True
    ).range(offset, offset + limit - 1).execute()

    return [
        CommunityMember(
            person_id=m["person_id"],
            display_name=m["display_name"],
            telegram_id=m.get("telegram_id"),
            created_at=m["created_at"]
        )
        for m in result.data or []
    ]


@router.delete("/{community_id}")
async def deactivate_community(
    community_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Deactivate community (soft delete).

    Members remain but can't join anymore.
    Only owner can deactivate.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Check ownership
    try:
        check = supabase.table("community").select(
            "owner_id"
        ).eq("community_id", community_id).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Community not found")

    if not check.data or check.data["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Soft delete
    supabase.table("community").update({
        "is_active": False
    }).eq("community_id", community_id).execute()

    return {"status": "deactivated"}
