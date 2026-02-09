"""
Proactive Questions API

Endpoints for managing proactive questions that help fill profile gaps.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.gap_detection import get_gap_detection_service

router = APIRouter(prefix="/questions", tags=["questions"])


class QuestionResponse(BaseModel):
    question_id: str
    person_id: Optional[str]
    person_name: Optional[str]
    question_type: str
    question_text: str
    question_text_ru: Optional[str]
    priority: float
    status: str
    created_at: str


class RespondRequest(BaseModel):
    action: str = Field(..., description="One of: answer, dismiss, snooze")
    answer_text: Optional[str] = Field(None, description="Answer text if action=answer")


class RespondResponse(BaseModel):
    success: bool
    message: str
    assertion_created: bool = False


class GenerateQuestionsResponse(BaseModel):
    generated_count: int
    questions: list[dict]


def _check_rate_limit(supabase, user_id: str, settings) -> tuple[bool, Optional[str]]:
    """
    Check if user can receive more questions.
    Returns (can_receive, reason_if_not)
    """
    # Get or create rate limit record
    rate_result = supabase.from_("question_rate_limit").select("*").eq(
        "owner_id", user_id
    ).execute()

    now = datetime.utcnow()
    today = now.date()

    if not rate_result.data:
        # Create new rate limit record
        supabase.from_("question_rate_limit").insert({
            "owner_id": user_id,
            "questions_shown_today": 0,
            "consecutive_dismisses": 0,
            "last_daily_reset": str(today)
        }).execute()
        return True, None

    rate = rate_result.data[0]

    # Check if paused
    if rate.get("paused_until"):
        paused_until = datetime.fromisoformat(rate["paused_until"].replace("Z", "+00:00"))
        if now < paused_until:
            return False, f"Questions paused until {paused_until.date()}"

    # Reset daily counter if needed
    last_reset = datetime.strptime(rate["last_daily_reset"], "%Y-%m-%d").date()
    if today > last_reset:
        supabase.from_("question_rate_limit").update({
            "questions_shown_today": 0,
            "last_daily_reset": str(today),
            "updated_at": "now()"
        }).eq("owner_id", user_id).execute()
        rate["questions_shown_today"] = 0

    # Check daily limit
    if rate["questions_shown_today"] >= settings.questions_max_per_day:
        return False, f"Daily question limit reached ({settings.questions_max_per_day})"

    # Check cooldown
    if rate.get("last_question_at"):
        last_question = datetime.fromisoformat(rate["last_question_at"].replace("Z", "+00:00"))
        cooldown = timedelta(hours=settings.questions_cooldown_hours)
        if now - last_question < cooldown:
            remaining = cooldown - (now - last_question)
            return False, f"Cooldown: {int(remaining.total_seconds() / 60)} minutes remaining"

    return True, None


def _update_rate_limit_on_show(supabase, user_id: str):
    """Update rate limit when a question is shown."""
    supabase.from_("question_rate_limit").upsert({
        "owner_id": user_id,
        "questions_shown_today": supabase.rpc("increment_questions_shown", {"p_user_id": user_id}).execute().data or 1,
        "last_question_at": datetime.utcnow().isoformat(),
        "updated_at": "now()"
    }, on_conflict="owner_id").execute()

    # Simpler approach: just update
    result = supabase.from_("question_rate_limit").select("questions_shown_today").eq(
        "owner_id", user_id
    ).execute()

    current = result.data[0]["questions_shown_today"] if result.data else 0

    supabase.from_("question_rate_limit").update({
        "questions_shown_today": current + 1,
        "last_question_at": datetime.utcnow().isoformat(),
        "updated_at": "now()"
    }).eq("owner_id", user_id).execute()


def _update_rate_limit_on_dismiss(supabase, user_id: str, settings):
    """Update rate limit when a question is dismissed."""
    result = supabase.from_("question_rate_limit").select("consecutive_dismisses").eq(
        "owner_id", user_id
    ).execute()

    current = result.data[0]["consecutive_dismisses"] if result.data else 0
    new_count = current + 1

    update_data = {
        "consecutive_dismisses": new_count,
        "updated_at": "now()"
    }

    # Pause if too many dismisses
    if new_count >= settings.questions_max_consecutive_dismisses:
        pause_until = datetime.utcnow() + timedelta(days=settings.questions_pause_days_after_dismisses)
        update_data["paused_until"] = pause_until.isoformat()

    supabase.from_("question_rate_limit").update(update_data).eq("owner_id", user_id).execute()


def _reset_consecutive_dismisses(supabase, user_id: str):
    """Reset consecutive dismisses when user answers a question."""
    supabase.from_("question_rate_limit").update({
        "consecutive_dismisses": 0,
        "paused_until": None,
        "updated_at": "now()"
    }).eq("owner_id", user_id).execute()


@router.get("/next", response_model=Optional[QuestionResponse])
async def get_next_question(
    person_id: Optional[str] = None,
    context: Optional[str] = None,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get the next proactive question for the user.

    Query params:
    - person_id: Get question specifically about this person
    - context: Context hint (e.g., "chat", "person_page")
    """
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Check rate limit
    can_receive, reason = _check_rate_limit(supabase, user_id, settings)
    if not can_receive:
        return None  # Silently return no question

    # Build query
    query = supabase.from_("proactive_question").select(
        "*, person:person_id(display_name)"
    ).eq("owner_id", user_id).eq("status", "pending")

    if person_id:
        query = query.eq("person_id", person_id)

    # Exclude expired
    query = query.gt("expires_at", datetime.utcnow().isoformat())

    # Order by priority desc
    query = query.order("priority", desc=True).limit(1)

    result = query.execute()

    if not result.data:
        # Try to generate new questions if none exist
        gap_service = get_gap_detection_service()
        await gap_service.generate_questions_batch(UUID(user_id), limit=3)

        # Query again
        result = query.execute()
        if not result.data:
            return None

    question = result.data[0]

    # Mark as shown
    supabase.from_("proactive_question").update({
        "status": "shown",
        "shown_at": datetime.utcnow().isoformat()
    }).eq("question_id", question["question_id"]).execute()

    # Update rate limit
    _update_rate_limit_on_show(supabase, user_id)

    person_name = None
    if question.get("person") and question["person"]:
        person_name = question["person"].get("display_name")

    return QuestionResponse(
        question_id=question["question_id"],
        person_id=question.get("person_id"),
        person_name=person_name,
        question_type=question["question_type"],
        question_text=question["question_text"],
        question_text_ru=question.get("question_text_ru"),
        priority=question["priority"],
        status="shown",
        created_at=question["created_at"]
    )


@router.post("/{question_id}/respond", response_model=RespondResponse)
async def respond_to_question(
    question_id: str,
    request: RespondRequest,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Respond to a proactive question.

    Actions:
    - answer: Provide an answer (requires answer_text)
    - dismiss: Dismiss the question
    - snooze: Delay the question for later
    """
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Verify question belongs to user
    question_result = supabase.from_("proactive_question").select(
        "*, person:person_id(person_id, display_name)"
    ).eq("question_id", question_id).eq("owner_id", user_id).execute()

    if not question_result.data:
        raise HTTPException(status_code=404, detail="Question not found")

    question = question_result.data[0]

    if request.action == "answer":
        if not request.answer_text:
            raise HTTPException(status_code=400, detail="answer_text required for answer action")

        # Update question status
        supabase.from_("proactive_question").update({
            "status": "answered",
            "answer_text": request.answer_text,
            "answered_at": datetime.utcnow().isoformat()
        }).eq("question_id", question_id).execute()

        # Create assertion from answer if we have a person
        assertion_created = False
        if question.get("person_id"):
            from app.services.embedding import generate_embedding

            # Map question type to predicate
            predicate_map = {
                "contact_context": "contact_context",
                "contact_info": "intro_path",
                "competencies": "can_help_with",
                "work_info": "works_at",
                "gap_fill": "note"
            }
            predicate = predicate_map.get(question["question_type"], "note")

            embedding = generate_embedding(request.answer_text)

            supabase.from_("assertion").insert({
                "subject_person_id": question["person_id"],
                "predicate": predicate,
                "object_value": request.answer_text,
                "embedding": embedding,
                "confidence": 0.9,
                "scope": "personal"
            }).execute()
            assertion_created = True

        # Reset consecutive dismisses
        _reset_consecutive_dismisses(supabase, user_id)

        return RespondResponse(
            success=True,
            message="Thank you for the information!",
            assertion_created=assertion_created
        )

    elif request.action == "dismiss":
        supabase.from_("proactive_question").update({
            "status": "dismissed"
        }).eq("question_id", question_id).execute()

        # Update dismiss counter
        _update_rate_limit_on_dismiss(supabase, user_id, settings)

        return RespondResponse(
            success=True,
            message="Question dismissed"
        )

    elif request.action == "snooze":
        # Extend expiration and reset status to pending
        new_expiry = datetime.utcnow() + timedelta(days=3)
        supabase.from_("proactive_question").update({
            "status": "pending",
            "expires_at": new_expiry.isoformat(),
            "priority": question["priority"] * 0.8  # Reduce priority slightly
        }).eq("question_id", question_id).execute()

        return RespondResponse(
            success=True,
            message="Question snoozed for 3 days"
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


@router.post("/generate", response_model=GenerateQuestionsResponse)
async def generate_questions(
    limit: int = 5,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Manually trigger question generation.
    This is mainly for testing; questions are auto-generated when needed.
    """
    user_id = get_user_id(token_payload)
    gap_service = get_gap_detection_service()

    questions = await gap_service.generate_questions_batch(UUID(user_id), limit=limit)

    return GenerateQuestionsResponse(
        generated_count=len(questions),
        questions=questions
    )


@router.get("/rate-limit")
async def get_rate_limit_status(
    token_payload: dict = Depends(verify_supabase_token)
):
    """Get current rate limit status for questions."""
    settings = get_settings()
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    can_receive, reason = _check_rate_limit(supabase, user_id, settings)

    result = supabase.from_("question_rate_limit").select("*").eq(
        "owner_id", user_id
    ).execute()

    rate = result.data[0] if result.data else {
        "questions_shown_today": 0,
        "consecutive_dismisses": 0
    }

    return {
        "can_receive_question": can_receive,
        "reason": reason,
        "questions_shown_today": rate.get("questions_shown_today", 0),
        "daily_limit": settings.questions_max_per_day,
        "consecutive_dismisses": rate.get("consecutive_dismisses", 0),
        "paused_until": rate.get("paused_until")
    }
