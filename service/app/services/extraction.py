import json
from typing import Optional
from dataclasses import dataclass
from openai import OpenAI
from app.config import get_settings
from app.agents.prompts import EXTRACTION_SYSTEM_PROMPT
from app.agents.schemas import ExtractionResult
from app.services.embedding import generate_embeddings_batch, create_assertion_text
from app.utils import normalize_linkedin_url


@dataclass
class ExtractionPipelineResult:
    """Result of processing extraction through the pipeline."""
    person_map: dict[str, str]  # temp_id -> person_id
    people_count: int
    assertions_count: int
    edges_count: int
    people_names: list[str]


def process_extraction_result(
    supabase,
    user_id: str,
    evidence_id: str,
    extraction: ExtractionResult,
    logger=None
) -> ExtractionPipelineResult:
    """
    Process extraction result: create persons, identities, assertions, edges.

    This is the SINGLE SOURCE OF TRUTH for extraction processing.
    Used by both Telegram bot handlers and API endpoints.

    Args:
        supabase: Supabase client (admin)
        user_id: Owner user ID
        evidence_id: Raw evidence ID to link assertions
        extraction: Extracted people/assertions/edges from GPT-4o
        logger: Optional logger (uses print if None)

    Returns:
        ExtractionPipelineResult with person_map and stats
    """
    def log(msg: str):
        if logger:
            logger.info(msg)
        else:
            print(f"[EXTRACTION] {msg}")

    person_map: dict[str, str] = {}  # temp_id -> person_id
    people_names: list[str] = []

    # 1. Create person records and identities
    for person in extraction.people:
        # Create person
        person_result = supabase.table("person").insert({
            "owner_id": user_id,
            "display_name": person.name,
            "status": "active"
        }).execute()

        person_id = person_result.data[0]["person_id"]
        person_map[person.temp_id] = person_id
        people_names.append(person.name)

        # Build identities list
        identities = [{"person_id": person_id, "namespace": "freeform_name", "value": person.name}]

        # Add name variations
        for variation in person.name_variations:
            if variation and variation != person.name:
                identities.append({
                    "person_id": person_id,
                    "namespace": "freeform_name",
                    "value": variation
                })

        # Add structured identifiers (with normalization)
        if person.identifiers.telegram:
            tg_value = person.identifiers.telegram.lstrip('@')
            if tg_value:
                identities.append({
                    "person_id": person_id,
                    "namespace": "telegram_username",
                    "value": tg_value
                })

        if person.identifiers.email:
            identities.append({
                "person_id": person_id,
                "namespace": "email",
                "value": person.identifiers.email.lower()
            })

        if person.identifiers.linkedin:
            normalized_linkedin = normalize_linkedin_url(person.identifiers.linkedin)
            if normalized_linkedin:
                identities.append({
                    "person_id": person_id,
                    "namespace": "linkedin_url",
                    "value": normalized_linkedin
                })

        if person.identifiers.phone:
            phone_value = person.identifiers.phone
            if phone_value:
                normalized = ''.join(c for c in phone_value if c.isdigit() or c == '+')
                if normalized:
                    identities.append({
                        "person_id": person_id,
                        "namespace": "phone",
                        "value": normalized
                    })

        # Insert identities (ignore duplicates)
        for identity in identities:
            try:
                supabase.table("identity").insert(identity).execute()
            except Exception:
                pass  # Ignore duplicate identities

    log(f"Created {len(person_map)} people")

    # 2. Create assertions with embeddings
    assertions_count = 0
    if extraction.assertions:
        # Generate texts for embedding
        assertion_texts = []
        for assertion in extraction.assertions:
            person_name = ""
            for p in extraction.people:
                if p.temp_id == assertion.subject:
                    person_name = p.name
                    break
            text = create_assertion_text(assertion.predicate, assertion.value, person_name)
            assertion_texts.append(text)

        # Generate embeddings in batch
        embeddings = generate_embeddings_batch(assertion_texts)

        # Insert assertions with embeddings
        for i, assertion in enumerate(extraction.assertions):
            person_id = person_map.get(assertion.subject)
            if not person_id:
                continue

            supabase.table("assertion").insert({
                "subject_person_id": person_id,
                "predicate": assertion.predicate,
                "object_value": assertion.value,
                "confidence": assertion.confidence,
                "evidence_id": evidence_id,
                "scope": "personal",
                "embedding": embeddings[i] if i < len(embeddings) else None
            }).execute()
            assertions_count += 1

    log(f"Created {assertions_count} assertions")

    # 3. Create edges
    edges_count = 0
    for edge in extraction.edges:
        src_id = person_map.get(edge.source)
        dst_id = person_map.get(edge.target)

        if src_id and dst_id and src_id != dst_id:
            try:
                supabase.table("edge").insert({
                    "src_person_id": src_id,
                    "dst_person_id": dst_id,
                    "edge_type": edge.type,
                    "scope": "personal"
                }).execute()
                edges_count += 1
            except Exception:
                pass  # Ignore edge errors

    log(f"Created {edges_count} edges")

    return ExtractionPipelineResult(
        person_map=person_map,
        people_count=len(person_map),
        assertions_count=assertions_count,
        edges_count=edges_count,
        people_names=people_names
    )


def extract_from_text_simple(text: str) -> ExtractionResult:
    """
    Fallback extraction using regular JSON mode (if strict schema fails).
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT + "\n\nRespond with valid JSON matching the schema."},
            {"role": "user", "content": f"""Extract information from this note and return JSON with this structure:
{{
  "people": [{{ "temp_id": "p1", "name": "...", "name_variations": [], "identifiers": {{}} }}],
  "assertions": [{{ "subject": "p1", "predicate": "works_at", "value": "...", "confidence": 0.8 }}],
  "edges": [{{ "source": "p1", "target": "p2", "type": "knows", "context": "..." }}]
}}

IMPORTANT - ALLOWED PREDICATES (you MUST use ONLY these):
- works_at: current company/organization
- role_is: current job title/role
- strong_at: skills, expertise (e.g., "frontend development", "ML")
- can_help_with: specific things they can help with
- worked_on: notable projects or achievements
- background: education, career history (e.g., "entrepreneur", "founded 3 companies")
- located_in: current location
- speaks_language: languages
- interested_in: hobbies, interests (e.g., "meditation", "kitesurfing")
- reputation_note: what others say
- contact_context: how we met
- relationship_depth: shared experiences
- recommend_for: recommended for specific areas
- not_recommend_for: not recommended for specific areas

BREAK DOWN into multiple assertions! Don't lump everything into one "note" - use specific predicates above.

Note:
{text}"""}
        ],
        response_format={"type": "json_object"},
        temperature=0.1
    )

    result_json = response.choices[0].message.content
    result_dict = json.loads(result_json)

    # Handle missing fields
    result_dict.setdefault("people", [])
    result_dict.setdefault("assertions", [])
    result_dict.setdefault("edges", [])

    return ExtractionResult(**result_dict)
