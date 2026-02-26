"""
Self-Profile API.

Endpoints for community members to manage their own profile.
Access is by telegram_id (they may not have full Supabase account).
"""

import json
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embeddings_batch, create_assertion_text
from app.agents.self_intro_prompt import (
    SELF_INTRO_SYSTEM_PROMPT,
    SELF_INTRO_PREDICATE_MAP
)
from app.config import get_settings

router = APIRouter(prefix="/profile", tags=["profile"])


# ============================================
# Request/Response Models
# ============================================

class SelfAssertion(BaseModel):
    predicate: str
    value: str


class SelfProfileResponse(BaseModel):
    person_id: str
    display_name: str
    community_id: str
    community_name: str
    assertions: List[SelfAssertion]
    created_at: str


class CreateProfileRequest(BaseModel):
    """Request to create/update profile from text or voice transcript."""
    community_id: str
    text: Optional[str] = None
    voice_url: Optional[str] = None


class ProcessingResult(BaseModel):
    person_id: str
    display_name: str
    assertions_created: int
    preview: dict  # Extracted data for confirmation


class DeleteResult(BaseModel):
    deleted: bool
    person_id: str


# ============================================
# Helper Functions
# ============================================

def extract_self_intro(text: str) -> dict:
    """
    Extract structured data from self-introduction text.

    Uses GPT-4o with self-intro specific prompt.

    Returns dict with: name, current_role, can_help_with, looking_for, etc.
    """
    import openai
    settings = get_settings()
    client = openai.OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SELF_INTRO_SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract information from this self-introduction:\n\n{text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    result_json = response.choices[0].message.content
    return json.loads(result_json)


def create_self_assertions(
    extraction: dict,
    person_id: str,
    evidence_id: str
) -> list[dict]:
    """
    Convert extraction result to assertion records.

    Args:
        extraction: Dict from extract_self_intro
        person_id: Person UUID
        evidence_id: Evidence UUID for linking

    Returns:
        List of assertion dicts ready for insert
    """
    assertions = []

    # Single value fields
    for field, predicate in SELF_INTRO_PREDICATE_MAP.items():
        value = extraction.get(field)
        if not value:
            continue

        if isinstance(value, list):
            # Multiple assertions for list fields
            for item in value:
                if item:
                    assertions.append({
                        "subject_person_id": person_id,
                        "predicate": predicate,
                        "object_value": item,
                        "evidence_id": evidence_id,
                        "scope": "personal",
                        "confidence": 0.9  # Self-reported = high confidence
                    })
        else:
            # Single assertion
            assertions.append({
                "subject_person_id": person_id,
                "predicate": predicate,
                "object_value": value,
                "evidence_id": evidence_id,
                "scope": "personal",
                "confidence": 0.9
            })

    return assertions


# ============================================
# Endpoints
# ============================================

@router.get("/me", response_model=Optional[SelfProfileResponse])
async def get_my_profile(
    community_id: str = Query(..., description="Community ID"),
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get my profile in a community.

    Looks up person by telegram_id from auth token.
    Returns None (204) if no profile exists yet.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get telegram_id from user metadata
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        telegram_id = user.user.user_metadata.get("telegram_id")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify user")

    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id associated with account")

    # Find person by telegram_id + community_id
    result = supabase.table("person").select(
        "person_id, display_name, community_id, created_at, community:community_id(name)"
    ).eq("telegram_id", telegram_id).eq("community_id", community_id).eq(
        "status", "active"
    ).execute()

    if not result.data:
        return None  # No profile yet

    person = result.data[0]

    # Get assertions
    assertions_result = supabase.table("assertion").select(
        "predicate, object_value"
    ).eq("subject_person_id", person["person_id"]).execute()

    return SelfProfileResponse(
        person_id=person["person_id"],
        display_name=person["display_name"],
        community_id=person["community_id"],
        community_name=person["community"]["name"] if person.get("community") else "Unknown",
        assertions=[
            SelfAssertion(predicate=a["predicate"], value=a["object_value"])
            for a in assertions_result.data or []
            if not a["predicate"].startswith("_")  # Filter out system predicates
        ],
        created_at=person["created_at"]
    )


@router.post("/me", response_model=ProcessingResult)
async def create_or_update_profile(
    req: CreateProfileRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Create or update my profile in a community.

    If profile exists, adds new assertions from text.
    If profile doesn't exist, creates person + assertions.

    The text is processed through self-intro extraction to get structured data.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get telegram_id
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        telegram_id = user.user.user_metadata.get("telegram_id")
        display_name = user.user.user_metadata.get("display_name", "Unknown")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify user")

    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id associated with account")

    # Validate community exists
    community_check = supabase.table("community").select(
        "community_id, owner_id, name"
    ).eq("community_id", req.community_id).eq("is_active", True).execute()

    if not community_check.data:
        raise HTTPException(status_code=404, detail="Community not found")

    community = community_check.data[0]

    # Get text from request (voice_url would be transcribed first, but that's handled by bot)
    text = req.text
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Extract structured data from self-intro
    extraction = extract_self_intro(text)

    # Get name from extraction, fallback to telegram display_name
    extracted_name = extraction.get("name", display_name)

    # Check if person already exists in this community
    existing = supabase.table("person").select(
        "person_id"
    ).eq("telegram_id", telegram_id).eq("community_id", req.community_id).eq(
        "status", "active"
    ).execute()

    # Create raw_evidence record
    evidence_result = supabase.table("raw_evidence").insert({
        "owner_id": community["owner_id"],  # Community owner owns the data
        "source_type": "text_note",
        "content": text,
        "processing_status": "done",
        "processed": True
    }).execute()

    evidence_id = evidence_result.data[0]["evidence_id"]

    if existing.data:
        # Update existing profile - add new assertions
        person_id = existing.data[0]["person_id"]

        # Optionally update display_name if extraction found one
        if extracted_name:
            supabase.table("person").update({
                "display_name": extracted_name
            }).eq("person_id", person_id).execute()
    else:
        # Create new person
        person_result = supabase.table("person").insert({
            "owner_id": community["owner_id"],  # Community owner owns the data
            "display_name": extracted_name,
            "telegram_id": telegram_id,
            "community_id": req.community_id,
            "status": "active"
        }).execute()

        person_id = person_result.data[0]["person_id"]

        # Add identity for name
        supabase.table("identity").insert({
            "person_id": person_id,
            "namespace": "freeform_name",
            "value": extracted_name
        }).execute()

    # Create assertions from extraction
    assertions = create_self_assertions(extraction, person_id, evidence_id)

    if assertions:
        # Generate embeddings
        assertion_texts = [
            create_assertion_text(a["predicate"], a["object_value"], extracted_name)
            for a in assertions
        ]
        embeddings = generate_embeddings_batch(assertion_texts)

        # Insert with embeddings
        for i, assertion in enumerate(assertions):
            assertion["embedding"] = embeddings[i] if i < len(embeddings) else None
            supabase.table("assertion").insert(assertion).execute()

    return ProcessingResult(
        person_id=person_id,
        display_name=extracted_name,
        assertions_created=len(assertions),
        preview=extraction
    )


@router.delete("/me", response_model=DeleteResult)
async def delete_my_profile(
    community_id: str = Query(..., description="Community ID"),
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Delete my profile from a community.

    Soft delete - sets status to 'deleted'.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get telegram_id
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        telegram_id = user.user.user_metadata.get("telegram_id")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify user")

    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram_id associated with account")

    # Find person
    result = supabase.table("person").select(
        "person_id"
    ).eq("telegram_id", telegram_id).eq("community_id", community_id).eq(
        "status", "active"
    ).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    person_id = result.data[0]["person_id"]

    # Soft delete
    supabase.table("person").update({
        "status": "deleted"
    }).eq("person_id", person_id).execute()

    return DeleteResult(deleted=True, person_id=person_id)


@router.get("/communities", response_model=list[dict])
async def get_my_communities(
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get list of communities where I have a profile.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get telegram_id
    try:
        user = supabase.auth.admin.get_user_by_id(user_id)
        telegram_id = user.user.user_metadata.get("telegram_id")
    except Exception:
        raise HTTPException(status_code=401, detail="Could not verify user")

    if not telegram_id:
        return []

    # Get communities where user has a profile
    result = supabase.table("person").select(
        "person_id, community_id, created_at, community:community_id(name, community_id)"
    ).eq("telegram_id", telegram_id).not_.is_("community_id", "null").eq(
        "status", "active"
    ).execute()

    communities = []
    for row in result.data or []:
        if row.get("community"):
            communities.append({
                "community_id": row["community"]["community_id"],
                "name": row["community"]["name"],
                "person_id": row["person_id"],
                "joined_at": row["created_at"]
            })

    return communities
