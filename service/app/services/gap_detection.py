"""
Gap Detection Service

Analyzes person profiles for missing information and generates
proactive questions to fill gaps.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from ..supabase_client import get_supabase_admin


@dataclass
class ProfileCompleteness:
    """Profile completeness analysis result."""
    completeness_score: float  # 0-1
    has_contact_context: bool
    has_relationship_depth: bool
    has_contact_info: bool
    has_competencies: bool
    has_work_info: bool
    has_location: bool
    total_assertions: int
    missing_fields: list[str]


@dataclass
class GapQuestion:
    """A generated question to fill a profile gap."""
    question_type: str
    question_text: str
    question_text_ru: str
    priority: float
    metadata: dict


# Question templates by gap type
QUESTION_TEMPLATES = {
    "contact_context": {
        "en": "How and where did you meet {name}?",
        "ru": "Где и как вы познакомились с {name}?",
        "priority": 0.95,  # Highest priority - origin of relationship
    },
    "relationship_depth": {
        "en": "What have you done together with {name}? Worked on projects, traveled, just hung out?",
        "ru": "Что вы делали вместе с {name}? Работали над проектами, путешествовали, просто общались?",
        "priority": 0.9,  # Second highest - relationship depth
    },
    "contact_info": {
        "en": "How can you reach {name}? (Telegram, email, phone)",
        "ru": "Как связаться с {name}? (Telegram, email, телефон)",
        "priority": 0.75,
    },
    "competencies": {
        "en": "What is {name} good at? What can they help with?",
        "ru": "В чём силён {name}? С чем может помочь?",
        "priority": 0.7,
    },
    "work_info": {
        "en": "Where does {name} work? What's their role?",
        "ru": "Где работает {name}? Какая у него/неё роль?",
        "priority": 0.6,
    },
    "location": {
        "en": "Where is {name} located?",
        "ru": "Где живёт {name}?",
        "priority": 0.4,
    },
}


class GapDetectionService:
    """Service for detecting profile gaps and generating questions."""

    def __init__(self):
        self.supabase = get_supabase_admin()

    async def get_profile_completeness(self, person_id: UUID) -> ProfileCompleteness:
        """Calculate profile completeness for a person."""
        result = self.supabase.rpc(
            "calculate_profile_completeness",
            {"p_person_id": str(person_id)}
        ).execute()

        if not result.data:
            return ProfileCompleteness(
                completeness_score=0,
                has_contact_context=False,
                has_relationship_depth=False,
                has_contact_info=False,
                has_competencies=False,
                has_work_info=False,
                has_location=False,
                total_assertions=0,
                missing_fields=["contact_context", "relationship_depth", "contact_info", "competencies", "work_info", "location"]
            )

        row = result.data[0]
        return ProfileCompleteness(
            completeness_score=row["completeness_score"],
            has_contact_context=row["has_contact_context"],
            has_relationship_depth=row.get("has_relationship_depth", False),
            has_contact_info=row["has_contact_info"],
            has_competencies=row["has_competencies"],
            has_work_info=row["has_work_info"],
            has_location=row["has_location"],
            total_assertions=row["total_assertions"],
            missing_fields=row["missing_fields"]
        )

    def generate_gap_question(
        self,
        person_name: str,
        gap_type: str
    ) -> Optional[GapQuestion]:
        """Generate a question for a specific gap type."""
        template = QUESTION_TEMPLATES.get(gap_type)
        if not template:
            return None

        return GapQuestion(
            question_type=gap_type,
            question_text=template["en"].format(name=person_name),
            question_text_ru=template["ru"].format(name=person_name),
            priority=template["priority"],
            metadata={"gap_type": gap_type}
        )

    async def get_priority_question_for_person(
        self,
        person_id: UUID,
        person_name: str
    ) -> Optional[GapQuestion]:
        """Get the highest priority question for a person."""
        completeness = await self.get_profile_completeness(person_id)

        if not completeness.missing_fields:
            return None

        # Sort by priority and return first
        sorted_gaps = sorted(
            completeness.missing_fields,
            key=lambda x: QUESTION_TEMPLATES.get(x, {}).get("priority", 0),
            reverse=True
        )

        return self.generate_gap_question(person_name, sorted_gaps[0])

    async def get_people_needing_questions(
        self,
        owner_id: UUID,
        limit: int = 10
    ) -> list[dict]:
        """
        Get people who need questions, prioritizing:
        1. Newly created (< 7 days) - memory is fresh
        2. Low completeness score
        3. Haven't been asked recently
        """
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

        # Get active people with completeness info
        result = self.supabase.from_("person").select(
            "person_id, display_name, created_at"
        ).eq(
            "owner_id", str(owner_id)
        ).eq(
            "status", "active"
        ).order(
            "created_at", desc=True
        ).limit(50).execute()

        if not result.data:
            return []

        people_with_gaps = []
        for person in result.data:
            person_id = UUID(person["person_id"])
            completeness = await self.get_profile_completeness(person_id)

            if completeness.completeness_score >= 1.0:
                continue  # No gaps

            # Check if already has pending question
            pending = self.supabase.from_("proactive_question").select(
                "question_id"
            ).eq(
                "person_id", str(person_id)
            ).eq(
                "status", "pending"
            ).limit(1).execute()

            if pending.data:
                continue  # Already has question

            # Calculate priority
            is_new = person["created_at"] >= seven_days_ago
            priority = (1 - completeness.completeness_score) * (1.5 if is_new else 1.0)

            people_with_gaps.append({
                "person_id": person_id,
                "display_name": person["display_name"],
                "completeness": completeness,
                "priority": priority,
                "is_new": is_new
            })

        # Sort by priority and return top N
        people_with_gaps.sort(key=lambda x: x["priority"], reverse=True)
        return people_with_gaps[:limit]

    async def create_question_for_person(
        self,
        owner_id: UUID,
        person_id: UUID,
        person_name: str,
        question: GapQuestion
    ) -> Optional[dict]:
        """Create a proactive question in the database."""
        result = self.supabase.from_("proactive_question").insert({
            "owner_id": str(owner_id),
            "person_id": str(person_id),
            "question_type": question.question_type,
            "question_text": question.question_text,
            "question_text_ru": question.question_text_ru,
            "priority": question.priority,
            "metadata": question.metadata,
            "status": "pending"
        }).execute()

        return result.data[0] if result.data else None

    async def generate_questions_batch(
        self,
        owner_id: UUID,
        limit: int = 5
    ) -> list[dict]:
        """Generate questions for multiple people who need them."""
        people = await self.get_people_needing_questions(owner_id, limit)
        created_questions = []

        for person_data in people:
            question = await self.get_priority_question_for_person(
                person_data["person_id"],
                person_data["display_name"]
            )
            if question:
                created = await self.create_question_for_person(
                    owner_id,
                    person_data["person_id"],
                    person_data["display_name"],
                    question
                )
                if created:
                    created_questions.append(created)

        return created_questions


# Singleton instance
_gap_detection_service: Optional[GapDetectionService] = None


def get_gap_detection_service() -> GapDetectionService:
    global _gap_detection_service
    if _gap_detection_service is None:
        _gap_detection_service = GapDetectionService()
    return _gap_detection_service
