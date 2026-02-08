import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.agents.schemas import (
    ProcessVoiceRequest,
    ProcessTextRequest,
    ProcessResponse,
    ExtractionResult
)
from app.services.transcription import transcribe_from_storage
from app.services.extraction import extract_from_text_simple
from app.services.embedding import generate_embeddings_batch, create_assertion_text

router = APIRouter(prefix="/process", tags=["process"])


async def process_pipeline(
    evidence_id: str,
    user_id: str,
    content: str,
    is_voice: bool = False,
    storage_path: Optional[str] = None
):
    """
    Main processing pipeline:
    1. Update status to extracting
    2. Extract people, assertions, edges
    3. Generate embeddings
    4. Save to database
    5. Update status to done
    """
    print(f"[PIPELINE] Starting for {evidence_id}, content length: {len(content)}")
    supabase = get_supabase_admin()

    try:
        # Update status to extracting
        supabase.table("raw_evidence").update({
            "processing_status": "extracting"
        }).eq("evidence_id", evidence_id).execute()
        print(f"[PIPELINE] Status set to extracting")

        # Extract information
        print(f"[PIPELINE] Calling GPT-4o extraction...")
        extraction = extract_from_text_simple(content)
        print(f"[PIPELINE] Extracted {len(extraction.people)} people, {len(extraction.assertions)} assertions")

        # Create person records and map temp_ids to real UUIDs
        person_map: dict[str, str] = {}  # temp_id -> person_id

        for person in extraction.people:
            # Create person
            person_result = supabase.table("person").insert({
                "owner_id": user_id,
                "display_name": person.name,
                "status": "active"
            }).execute()

            person_id = person_result.data[0]["person_id"]
            person_map[person.temp_id] = person_id

            # Create identities for name variations
            identities = [{"person_id": person_id, "namespace": "freeform_name", "value": person.name}]

            for variation in person.name_variations:
                if variation and variation != person.name:
                    identities.append({
                        "person_id": person_id,
                        "namespace": "freeform_name",
                        "value": variation
                    })

            # Add identifiers
            if person.identifiers.telegram:
                identities.append({
                    "person_id": person_id,
                    "namespace": "telegram_username",
                    "value": person.identifiers.telegram
                })
            if person.identifiers.email:
                identities.append({
                    "person_id": person_id,
                    "namespace": "email_hash",
                    "value": person.identifiers.email
                })
            if person.identifiers.linkedin:
                identities.append({
                    "person_id": person_id,
                    "namespace": "linkedin_url",
                    "value": person.identifiers.linkedin
                })

            # Insert identities (ignore conflicts on unique constraint)
            for identity in identities:
                try:
                    supabase.table("identity").insert(identity).execute()
                except Exception:
                    pass  # Ignore duplicate identities

        # Prepare assertions with embeddings
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

        # Create edges
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
                except Exception:
                    pass  # Ignore edge errors

        # Update evidence status to done
        supabase.table("raw_evidence").update({
            "processed": True,
            "processing_status": "done"
        }).eq("evidence_id", evidence_id).execute()

    except Exception as e:
        # Update status to error
        supabase.table("raw_evidence").update({
            "processing_status": "error",
            "error_message": str(e)[:500]
        }).eq("evidence_id", evidence_id).execute()
        raise


@router.post("/voice", response_model=ProcessResponse)
async def process_voice(
    request: ProcessVoiceRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Process voice note from Supabase Storage.
    Transcribes audio, extracts information, and saves to database.
    """
    print(f"[VOICE] Received request: storage_path={request.storage_path}")
    user_id = get_user_id(token_payload)
    print(f"[VOICE] User ID: {user_id}")
    supabase = get_supabase_admin()

    # Create raw_evidence record
    evidence_result = supabase.table("raw_evidence").insert({
        "owner_id": user_id,
        "source_type": "voice_note",
        "content": "",  # Will be updated with transcript
        "audio_storage_path": request.storage_path,
        "processing_status": "transcribing"
    }).execute()

    evidence_id = evidence_result.data[0]["evidence_id"]

    async def process_voice_async():
        try:
            supabase_inner = get_supabase_admin()

            # Transcribe
            transcript = await transcribe_from_storage(request.storage_path)

            # Update evidence with transcript
            supabase_inner.table("raw_evidence").update({
                "content": transcript
            }).eq("evidence_id", evidence_id).execute()

            # Run extraction pipeline
            await process_pipeline(evidence_id, user_id, transcript, is_voice=True, storage_path=request.storage_path)

        except Exception as e:
            supabase_inner = get_supabase_admin()
            supabase_inner.table("raw_evidence").update({
                "processing_status": "error",
                "error_message": str(e)[:500]
            }).eq("evidence_id", evidence_id).execute()

    # Run in background (just pass the coroutine function, FastAPI handles it)
    background_tasks.add_task(process_voice_async)

    return ProcessResponse(
        evidence_id=evidence_id,
        status="processing",
        message="Voice note processing started"
    )


@router.post("/text", response_model=ProcessResponse)
async def process_text(
    request: ProcessTextRequest,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Process text note.
    Extracts information and saves to database.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Create raw_evidence record
    evidence_result = supabase.table("raw_evidence").insert({
        "owner_id": user_id,
        "source_type": "text_note",
        "content": request.text,
        "processing_status": "extracting"
    }).execute()

    evidence_id = evidence_result.data[0]["evidence_id"]

    async def process_text_async():
        print(f"[TEXT] Starting background processing for {evidence_id}")
        try:
            await process_pipeline(evidence_id, user_id, request.text)
            print(f"[TEXT] Completed processing for {evidence_id}")
        except Exception as e:
            print(f"[TEXT] Error processing {evidence_id}: {e}")
            supabase_inner = get_supabase_admin()
            supabase_inner.table("raw_evidence").update({
                "processing_status": "error",
                "error_message": str(e)[:500]
            }).eq("evidence_id", evidence_id).execute()

    # Run in background (just pass the coroutine function, FastAPI handles it)
    background_tasks.add_task(process_text_async)

    return ProcessResponse(
        evidence_id=evidence_id,
        status="processing",
        message="Text note processing started"
    )


@router.get("/status/{evidence_id}")
async def get_processing_status(
    evidence_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """Get processing status of an evidence record."""
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    result = supabase.table("raw_evidence").select(
        "evidence_id, processing_status, processed, error_message"
    ).eq("evidence_id", evidence_id).eq("owner_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evidence not found")

    evidence = result.data[0]

    # Count extracted data if done
    people_count = None
    assertions_count = None

    if evidence["processed"]:
        # This is a simplified count - in production would join properly
        pass

    return {
        "evidence_id": evidence["evidence_id"],
        "status": evidence["processing_status"],
        "processed": evidence["processed"],
        "error_message": evidence.get("error_message")
    }
