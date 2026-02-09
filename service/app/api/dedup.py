"""
Deduplication API

Endpoints for detecting and merging duplicate people.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.dedup import get_dedup_service

router = APIRouter(prefix="/dedup", tags=["deduplication"])


class DuplicatePair(BaseModel):
    person_a_id: str
    person_a_name: str
    person_b_id: str
    person_b_name: str
    match_type: str
    match_score: float
    match_details: dict


class CandidatesResponse(BaseModel):
    candidates: list[DuplicatePair]
    total: int


class MergeRequest(BaseModel):
    keep_person_id: str = Field(..., description="ID of the person to keep")
    merge_person_id: str = Field(..., description="ID of the person to merge into the kept one")


class MergeResponse(BaseModel):
    success: bool
    kept_person_id: str
    merged_person_id: str
    assertions_moved: int
    edges_moved: int
    identities_moved: int


class RejectRequest(BaseModel):
    person_a_id: str
    person_b_id: str


class RejectResponse(BaseModel):
    success: bool
    message: str


@router.get("/candidates", response_model=CandidatesResponse)
async def get_duplicate_candidates(
    limit: int = 20,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get list of potential duplicate people in the network.

    Returns pairs of people who might be the same person, ranked by confidence.
    """
    user_id = get_user_id(token_payload)
    dedup_service = get_dedup_service()

    candidates = await dedup_service.find_all_duplicates(UUID(user_id), limit=limit)

    pairs = []
    for c in candidates:
        pairs.append(DuplicatePair(
            person_a_id=c["person_a"]["person_id"],
            person_a_name=c["person_a"]["display_name"],
            person_b_id=c["person_b"]["person_id"],
            person_b_name=c["person_b"]["display_name"],
            match_type=c["match_type"],
            match_score=c["match_score"],
            match_details=c["match_details"]
        ))

    return CandidatesResponse(
        candidates=pairs,
        total=len(pairs)
    )


@router.get("/candidates/{person_id}")
async def get_duplicates_for_person(
    person_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get potential duplicates for a specific person.
    """
    user_id = get_user_id(token_payload)
    dedup_service = get_dedup_service()

    # Verify person belongs to user
    supabase = get_supabase_admin()
    check = supabase.from_("person").select("person_id, display_name").eq(
        "person_id", person_id
    ).eq("owner_id", user_id).execute()

    if not check.data:
        raise HTTPException(status_code=404, detail="Person not found")

    candidates = await dedup_service.find_duplicates_for_person(
        UUID(user_id), UUID(person_id)
    )

    return {
        "person_id": person_id,
        "person_name": check.data[0]["display_name"],
        "duplicates": [
            {
                "person_id": str(c.person_id),
                "display_name": c.display_name,
                "match_type": c.match_type,
                "match_score": c.match_score,
                "match_details": c.match_details
            }
            for c in candidates
        ]
    }


@router.post("/merge", response_model=MergeResponse)
async def merge_people(
    request: MergeRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Merge two people into one.

    The person specified by 'keep_person_id' will be kept.
    All data from 'merge_person_id' will be moved to the kept person.
    The merged person will be marked as 'merged' status.
    """
    user_id = get_user_id(token_payload)
    dedup_service = get_dedup_service()

    try:
        result = await dedup_service.merge_persons(
            UUID(user_id),
            UUID(request.keep_person_id),
            UUID(request.merge_person_id)
        )

        return MergeResponse(
            success=True,
            kept_person_id=str(result.kept_person_id),
            merged_person_id=str(result.merged_person_id),
            assertions_moved=result.assertions_moved,
            edges_moved=result.edges_moved,
            identities_moved=result.identities_moved
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reject", response_model=RejectResponse)
async def reject_duplicate(
    request: RejectRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Mark two people as definitely NOT duplicates.

    This prevents them from being suggested as duplicates in the future.
    """
    user_id = get_user_id(token_payload)
    dedup_service = get_dedup_service()

    await dedup_service.reject_duplicate(
        UUID(user_id),
        UUID(request.person_a_id),
        UUID(request.person_b_id)
    )

    return RejectResponse(
        success=True,
        message="Marked as different people"
    )


@router.post("/auto-detect")
async def auto_detect_duplicates(
    limit: int = 5,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Auto-detect duplicates and create proactive questions for confirmation.

    This is typically called after importing new people or periodically.
    """
    user_id = get_user_id(token_payload)
    dedup_service = get_dedup_service()

    questions = await dedup_service.auto_detect_and_create_questions(
        UUID(user_id), limit=limit
    )

    return {
        "questions_created": len(questions),
        "questions": questions
    }
