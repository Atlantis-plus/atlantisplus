"""
Deduplication Service

Detects and merges duplicate person records.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..supabase_client import get_supabase_admin


@dataclass
class DuplicateCandidate:
    """A potential duplicate person."""
    person_id: UUID
    display_name: str
    match_type: str  # 'identity_match', 'name_similarity', 'embedding_similarity'
    match_score: float
    match_details: dict


@dataclass
class MergeResult:
    """Result of merging two people."""
    kept_person_id: UUID
    merged_person_id: UUID
    assertions_moved: int
    edges_moved: int
    identities_moved: int


class DeduplicationService:
    """Service for detecting and merging duplicate people."""

    def __init__(self):
        self.supabase = get_supabase_admin()

    async def find_duplicates_for_person(
        self,
        owner_id: UUID,
        person_id: UUID,
        name_threshold: float = 0.5,
        embedding_threshold: float = 0.85
    ) -> list[DuplicateCandidate]:
        """
        Find potential duplicates for a specific person.

        Uses:
        1. Identity matches (exact email, telegram, linkedin)
        2. Name similarity (pg_trgm)
        3. Embedding similarity (if both have embeddings)
        """
        result = self.supabase.rpc(
            "find_similar_people",
            {
                "p_owner_id": str(owner_id),
                "p_person_id": str(person_id),
                "p_name_threshold": name_threshold,
                "p_embedding_threshold": embedding_threshold
            }
        ).execute()

        if not result.data:
            return []

        candidates = []
        seen_ids = set()

        for row in result.data:
            pid = row["candidate_person_id"]
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            candidates.append(DuplicateCandidate(
                person_id=UUID(pid),
                display_name=row["candidate_name"],
                match_type=row["match_type"],
                match_score=row["match_score"],
                match_details=row["match_details"] or {}
            ))

        return candidates

    async def find_all_duplicates(
        self,
        owner_id: UUID,
        limit: int = 20
    ) -> list[dict]:
        """
        Find all potential duplicates in the user's network.
        Returns pairs of people who might be duplicates.
        """
        # Get all active people
        people = self.supabase.from_("person").select(
            "person_id, display_name"
        ).eq("owner_id", str(owner_id)).eq("status", "active").execute()

        if not people.data:
            return []

        all_candidates = []
        seen_pairs = set()

        for person in people.data:
            person_id = UUID(person["person_id"])
            candidates = await self.find_duplicates_for_person(
                owner_id, person_id
            )

            for candidate in candidates:
                # Create sorted pair to avoid duplicates
                pair = tuple(sorted([str(person_id), str(candidate.person_id)]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                all_candidates.append({
                    "person_a": {
                        "person_id": str(person_id),
                        "display_name": person["display_name"]
                    },
                    "person_b": {
                        "person_id": str(candidate.person_id),
                        "display_name": candidate.display_name
                    },
                    "match_type": candidate.match_type,
                    "match_score": candidate.match_score,
                    "match_details": candidate.match_details
                })

        # Sort by score descending
        all_candidates.sort(key=lambda x: x["match_score"], reverse=True)
        return all_candidates[:limit]

    async def create_dedup_question(
        self,
        owner_id: UUID,
        person_a_id: UUID,
        person_a_name: str,
        person_b_id: UUID,
        person_b_name: str,
        match_score: float
    ) -> Optional[dict]:
        """Create a proactive question for dedup confirmation."""
        # Check if question already exists
        existing = self.supabase.from_("proactive_question").select(
            "question_id"
        ).eq("owner_id", str(owner_id)).eq("question_type", "dedup_confirm").eq(
            "status", "pending"
        ).execute()

        # Check if this specific pair already has a question
        for q in existing.data or []:
            q_detail = self.supabase.from_("proactive_question").select(
                "metadata"
            ).eq("question_id", q["question_id"]).execute()
            if q_detail.data:
                meta = q_detail.data[0].get("metadata", {})
                if meta.get("candidate_person_id") in [str(person_a_id), str(person_b_id)]:
                    return None  # Already exists

        # Create question
        result = self.supabase.from_("proactive_question").insert({
            "owner_id": str(owner_id),
            "person_id": str(person_a_id),
            "question_type": "dedup_confirm",
            "question_text": f"Are {person_a_name} and {person_b_name} the same person?",
            "question_text_ru": f"{person_a_name} и {person_b_name} — это один и тот же человек?",
            "priority": min(0.95, match_score),  # High priority
            "metadata": {
                "candidate_person_id": str(person_b_id),
                "candidate_name": person_b_name,
                "match_score": match_score
            },
            "status": "pending"
        }).execute()

        return result.data[0] if result.data else None

    async def merge_persons(
        self,
        owner_id: UUID,
        keep_person_id: UUID,
        merge_person_id: UUID
    ) -> MergeResult:
        """
        Merge two people into one.

        - Keeps the 'keep_person_id' as the canonical record
        - Moves all assertions, edges, identities from merge_person to keep_person
        - Marks merge_person as 'merged'
        """
        # Verify both belong to owner
        check = self.supabase.from_("person").select("person_id").eq(
            "owner_id", str(owner_id)
        ).in_("person_id", [str(keep_person_id), str(merge_person_id)]).execute()

        if len(check.data) != 2:
            raise ValueError("Both people must belong to the owner")

        # Move assertions
        assertions_result = self.supabase.from_("assertion").update({
            "subject_person_id": str(keep_person_id)
        }).eq("subject_person_id", str(merge_person_id)).execute()
        assertions_moved = len(assertions_result.data) if assertions_result.data else 0

        # Move edges (both directions)
        edges_src = self.supabase.from_("edge").update({
            "src_person_id": str(keep_person_id)
        }).eq("src_person_id", str(merge_person_id)).execute()

        edges_dst = self.supabase.from_("edge").update({
            "dst_person_id": str(keep_person_id)
        }).eq("dst_person_id", str(merge_person_id)).execute()

        edges_moved = (
            (len(edges_src.data) if edges_src.data else 0) +
            (len(edges_dst.data) if edges_dst.data else 0)
        )

        # Remove self-referential edges that might have been created
        self.supabase.from_("edge").delete().eq(
            "src_person_id", str(keep_person_id)
        ).eq("dst_person_id", str(keep_person_id)).execute()

        # Move identities
        identities_result = self.supabase.from_("identity").update({
            "person_id": str(keep_person_id)
        }).eq("person_id", str(merge_person_id)).execute()
        identities_moved = len(identities_result.data) if identities_result.data else 0

        # Mark merged person
        self.supabase.from_("person").update({
            "status": "merged",
            "merged_into_person_id": str(keep_person_id),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("person_id", str(merge_person_id)).execute()

        # Update person_match_candidate if exists
        self.supabase.from_("person_match_candidate").update({
            "status": "merged"
        }).or_(
            f"a_person_id.eq.{merge_person_id},b_person_id.eq.{merge_person_id}"
        ).execute()

        return MergeResult(
            kept_person_id=keep_person_id,
            merged_person_id=merge_person_id,
            assertions_moved=assertions_moved,
            edges_moved=edges_moved,
            identities_moved=identities_moved
        )

    async def reject_duplicate(
        self,
        owner_id: UUID,
        person_a_id: UUID,
        person_b_id: UUID
    ) -> bool:
        """Mark two people as definitely NOT duplicates."""
        # Create or update match candidate as rejected
        self.supabase.from_("person_match_candidate").upsert({
            "owner_id": str(owner_id),
            "a_person_id": str(min(person_a_id, person_b_id, key=str)),
            "b_person_id": str(max(person_a_id, person_b_id, key=str)),
            "score": 0,
            "reasons": {"rejected_by_user": True},
            "status": "rejected"
        }, on_conflict="a_person_id,b_person_id").execute()

        # Dismiss any pending questions about this pair
        self.supabase.from_("proactive_question").update({
            "status": "dismissed"
        }).eq("person_id", str(person_a_id)).eq("question_type", "dedup_confirm").contains(
            "metadata", {"candidate_person_id": str(person_b_id)}
        ).execute()

        return True

    async def auto_detect_and_create_questions(
        self,
        owner_id: UUID,
        limit: int = 5
    ) -> list[dict]:
        """
        Auto-detect duplicates and create proactive questions for confirmation.
        Called periodically or after new people are added.
        """
        duplicates = await self.find_all_duplicates(owner_id, limit=limit * 2)
        created_questions = []

        for dup in duplicates:
            if len(created_questions) >= limit:
                break

            # Skip low-confidence matches for auto-questions
            if dup["match_score"] < 0.6:
                continue

            question = await self.create_dedup_question(
                owner_id,
                UUID(dup["person_a"]["person_id"]),
                dup["person_a"]["display_name"],
                UUID(dup["person_b"]["person_id"]),
                dup["person_b"]["display_name"],
                dup["match_score"]
            )

            if question:
                created_questions.append(question)

        return created_questions

    async def run_batch_dedup(
        self,
        owner_id: UUID,
        batch_id: str
    ) -> dict:
        """
        Run dedup specifically for newly imported batch.

        Compares each person from the batch against existing people
        (excluding others from the same batch) and creates match candidates.

        Returns dict with checked count and duplicates found.
        """
        # Get all people from this batch
        batch_people = self.supabase.from_("person").select(
            "person_id, display_name"
        ).eq("import_batch_id", batch_id).eq("status", "active").execute()

        if not batch_people.data:
            return {"checked": 0, "duplicates_found": 0}

        batch_person_ids = {p["person_id"] for p in batch_people.data}
        duplicates_found = 0
        seen_pairs = set()

        for person in batch_people.data:
            person_id = UUID(person["person_id"])

            # Find duplicates for this person
            candidates = await self.find_duplicates_for_person(
                owner_id, person_id,
                name_threshold=0.5,
                embedding_threshold=0.8
            )

            for candidate in candidates:
                # Skip if candidate is also from this batch
                if str(candidate.person_id) in batch_person_ids:
                    continue

                # Create sorted pair to avoid duplicates
                pair = tuple(sorted([str(person_id), str(candidate.person_id)]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                # Check if this pair already has a candidate record
                existing = self.supabase.from_("person_match_candidate").select(
                    "id"
                ).eq("a_person_id", pair[0]).eq("b_person_id", pair[1]).execute()

                if not existing.data:
                    # Create match candidate
                    try:
                        self.supabase.from_("person_match_candidate").insert({
                            "a_person_id": pair[0],
                            "b_person_id": pair[1],
                            "score": candidate.match_score,
                            "reasons": {
                                "match_type": candidate.match_type,
                                "batch_id": batch_id,
                                "new_person_name": person["display_name"],
                                "existing_person_name": candidate.display_name,
                                **candidate.match_details
                            },
                            "status": "pending"
                        }).execute()
                        duplicates_found += 1
                    except Exception as e:
                        print(f"[DEDUP] Failed to create match candidate: {e}")

        return {
            "checked": len(batch_people.data),
            "duplicates_found": duplicates_found
        }


# Singleton instance
_dedup_service: Optional[DeduplicationService] = None


def get_dedup_service() -> DeduplicationService:
    global _dedup_service
    if _dedup_service is None:
        _dedup_service = DeduplicationService()
    return _dedup_service
