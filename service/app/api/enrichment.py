"""
Enrichment API

Endpoints for enriching person profiles with external data.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.enrichment import get_enrichment_service

router = APIRouter(prefix="/enrich", tags=["enrichment"])


class QuotaResponse(BaseModel):
    daily_used: int
    daily_limit: int
    monthly_used: int
    monthly_limit: int
    can_enrich: bool
    reason: str | None


class EnrichResponse(BaseModel):
    success: bool
    person_id: str
    assertions_created: int
    identities_created: int
    error: str | None


class EnrichmentDetails(BaseModel):
    source: str
    facts_added: int
    identities_added: int
    timestamp: str


class StatusResponse(BaseModel):
    status: str  # 'enriched' | 'not_enriched' | 'processing' | 'error'
    last_enriched_at: str | None
    enrichment_details: EnrichmentDetails | None = None
    last_job: dict | None


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get current enrichment quota.

    Shows how many enrichments are remaining for the day and month.
    """
    user_id = get_user_id(token_payload)
    service = get_enrichment_service()

    quota = await service.get_quota(UUID(user_id))

    return QuotaResponse(
        daily_used=quota.daily_used,
        daily_limit=quota.daily_limit,
        monthly_used=quota.monthly_used,
        monthly_limit=quota.monthly_limit,
        can_enrich=quota.can_enrich,
        reason=quota.reason
    )


@router.post("/{person_id}", response_model=EnrichResponse)
async def enrich_person(
    person_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Enrich a person's profile with external data.

    Uses People Data Labs to look up additional information based on
    available identifiers (email, LinkedIn, name).

    Creates new assertions with scope='external' and adds missing identities.
    """
    user_id = get_user_id(token_payload)
    service = get_enrichment_service()

    result = await service.enrich_person(UUID(user_id), UUID(person_id))

    if not result.success and result.error:
        # Still return 200 but with error in response
        return EnrichResponse(
            success=False,
            person_id=person_id,
            assertions_created=0,
            identities_created=0,
            error=result.error
        )

    return EnrichResponse(
        success=result.success,
        person_id=str(result.person_id),
        assertions_created=result.assertions_created,
        identities_created=result.identities_created,
        error=result.error
    )


@router.get("/status/{person_id}", response_model=StatusResponse)
async def get_enrichment_status(
    person_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get enrichment status for a person.

    Shows whether the person has been enriched and details of the last attempt.
    """
    user_id = get_user_id(token_payload)
    service = get_enrichment_service()

    status = await service.get_enrichment_status(UUID(user_id), UUID(person_id))

    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Person not found")

    enrichment_details = None
    if status.get("enrichment_details"):
        details = status["enrichment_details"]
        enrichment_details = EnrichmentDetails(
            source=details.get("source", "unknown"),
            facts_added=details.get("facts_added", 0),
            identities_added=details.get("identities_added", 0),
            timestamp=details.get("timestamp", "")
        )

    return StatusResponse(
        status=status["status"],
        last_enriched_at=status.get("last_enriched_at"),
        enrichment_details=enrichment_details,
        last_job=status.get("last_job")
    )


@router.post("/{person_id}/background")
async def enrich_person_background(
    person_id: str,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Start enrichment in the background.

    Returns immediately with a pending status.
    Use GET /enrich/status/{person_id} to check progress.
    """
    user_id = get_user_id(token_payload)
    service = get_enrichment_service()

    # Check quota first
    quota = await service.get_quota(UUID(user_id))
    if not quota.can_enrich:
        return {
            "queued": False,
            "error": quota.reason
        }

    # Queue the enrichment
    async def do_enrich():
        await service.enrich_person(UUID(user_id), UUID(person_id))

    background_tasks.add_task(do_enrich)

    return {
        "queued": True,
        "person_id": person_id,
        "message": "Enrichment started. Check status endpoint for progress."
    }
