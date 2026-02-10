"""
LinkedIn CSV Import API.

Imports connections from LinkedIn CSV export.
"""

import csv
import io
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding
from app.services.dedup import get_dedup_service
from app.services.proactive import get_proactive_service
from app.services.import_analytics import calculate_linkedin_analytics

router = APIRouter(prefix="/import", tags=["import"])


class LinkedInContact(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    connected_on: Optional[str] = None


class ImportPreview(BaseModel):
    total_contacts: int
    with_email: int
    without_email: int
    sample: list[LinkedInContact]


class ImportResult(BaseModel):
    imported: int
    skipped: int
    duplicates_found: int
    updated: int
    batch_id: str
    evidence_id: str  # For frontend to subscribe to progress
    analytics: dict
    details: list[dict]
    dedup_result: Optional[dict] = None


def parse_linkedin_csv(content: str) -> list[LinkedInContact]:
    """
    Parse LinkedIn connections CSV.

    LinkedIn CSV format:
    First Name,Last Name,Email Address,Company,Position,Connected On
    """
    contacts = []

    # Try to detect encoding and parse
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        # Handle different possible column names
        first_name = row.get('First Name') or row.get('first_name') or ''
        last_name = row.get('Last Name') or row.get('last_name') or ''
        email = row.get('Email Address') or row.get('email') or row.get('Email') or None
        company = row.get('Company') or row.get('company') or None
        position = row.get('Position') or row.get('position') or row.get('Title') or None
        connected_on = row.get('Connected On') or row.get('connected_on') or None

        # Skip empty rows
        if not first_name and not last_name:
            continue

        # Clean up empty strings
        if email == '':
            email = None
        if company == '':
            company = None
        if position == '':
            position = None

        contacts.append(LinkedInContact(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email.strip() if email else None,
            company=company.strip() if company else None,
            position=position.strip() if position else None,
            connected_on=connected_on.strip() if connected_on else None
        ))

    return contacts


@router.post("/linkedin/preview", response_model=ImportPreview)
async def preview_linkedin_import(
    file: UploadFile = File(...),
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Preview LinkedIn CSV import without creating records.

    Returns count and sample of contacts.
    """
    # Read file content
    try:
        content = await file.read()
        # Try UTF-8 first, then latin-1
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Parse CSV
    try:
        contacts = parse_linkedin_csv(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found in CSV")

    # Calculate stats
    with_email = sum(1 for c in contacts if c.email)
    without_email = len(contacts) - with_email

    # Get sample (first 5)
    sample = contacts[:5]

    return ImportPreview(
        total_contacts=len(contacts),
        with_email=with_email,
        without_email=without_email,
        sample=sample
    )


@router.post("/linkedin", response_model=ImportResult)
async def import_linkedin_csv(
    file: UploadFile = File(...),
    skip_duplicates: bool = True,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Import LinkedIn connections from CSV.

    Creates person records with assertions for company, position, and connection date.
    Tracks import in batch table for analytics and rollback.
    Saves original file to Storage for audit trail.
    Creates raw_evidence with progress status for frontend.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Read file content
    try:
        content = await file.read()
        file_size = len(content)
        file_name = file.filename or 'connections.csv'
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Create raw_evidence immediately (status=pending) so frontend can subscribe
    evidence_result = supabase.table('raw_evidence').insert({
        'owner_id': user_id,
        'source_type': 'import',
        'content': f"LinkedIn import: processing {file_name}...",
        'metadata': {
            'import_type': 'linkedin',
            'file_name': file_name,
            'file_size': file_size
        },
        'processing_status': 'pending'
    }).execute()
    evidence_id = evidence_result.data[0]['evidence_id']

    def update_status(status: str, content: Optional[str] = None, error: Optional[str] = None):
        """Helper to update raw_evidence status"""
        update_data = {'processing_status': status}
        if content:
            update_data['content'] = content
        if error:
            update_data['error_message'] = error
        supabase.table('raw_evidence').update(update_data).eq('evidence_id', evidence_id).execute()

    # Parse CSV
    try:
        contacts = parse_linkedin_csv(text)
    except Exception as e:
        update_status('error', error=f"Failed to parse CSV: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not contacts:
        update_status('error', error="No contacts found in CSV")
        raise HTTPException(status_code=400, detail="No contacts found in CSV")

    # Calculate analytics
    contacts_for_analytics = [
        {
            'connected_on': c.connected_on,
            'company': c.company,
            'email': c.email
        }
        for c in contacts
    ]
    analytics = calculate_linkedin_analytics(contacts_for_analytics)

    # Create import batch for tracking
    batch_result = supabase.table('import_batch').insert({
        'owner_id': user_id,
        'import_type': 'linkedin',
        'total_contacts': len(contacts),
        'analytics': analytics
    }).execute()
    batch_id = batch_result.data[0]['batch_id']

    # Upload file to Storage
    storage_path = f"{user_id}/{batch_id}/{file_name}"
    try:
        supabase.storage.from_('imports').upload(
            storage_path,
            content,
            file_options={"content-type": "text/csv"}
        )
    except Exception as e:
        print(f"[LINKEDIN IMPORT] Failed to upload to storage: {e}")
        # Continue anyway - storage is nice-to-have

    # Update raw_evidence with batch_id and storage path
    supabase.table('raw_evidence').update({
        'storage_path': storage_path,
        'content': f"LinkedIn import: {len(contacts)} contacts",
        'metadata': {
            'import_type': 'linkedin',
            'batch_id': batch_id,
            'file_name': file_name,
            'file_size': file_size,
            'stats': {
                'contacts': len(contacts),
                'with_email': sum(1 for c in contacts if c.email)
            }
        },
        'processing_status': 'extracting'
    }).eq('evidence_id', evidence_id).execute()

    def rollback_batch(batch_id: str, error_msg: str):
        """Rollback all data created for this batch on error"""
        try:
            # Get all people created in this batch
            people = supabase.table('person').select('person_id').eq(
                'import_batch_id', batch_id
            ).execute()
            person_ids = [p['person_id'] for p in people.data] if people.data else []

            if person_ids:
                # Delete identities first
                supabase.table('identity').delete().in_('person_id', person_ids).execute()
                # Delete assertions
                supabase.table('assertion').delete().in_('subject_person_id', person_ids).execute()
                # Delete people
                supabase.table('person').delete().in_('person_id', person_ids).execute()

            # Mark batch as failed
            supabase.table('import_batch').update({
                'status': 'rolled_back'
            }).eq('batch_id', batch_id).execute()

            # Update evidence status
            update_status('error', error=error_msg)
        except Exception as e:
            print(f"[LINKEDIN IMPORT] Rollback failed: {e}")

    imported = 0
    updated = 0
    skipped = 0
    duplicates_found = 0
    details = []
    new_person_ids = []

    try:
        for contact in contacts:
            display_name = f"{contact.first_name} {contact.last_name}".strip()

            if not display_name:
                skipped += 1
                continue

            # Check for existing person with same name or email
            existing_person = None

            # Check by email only (name matching is too unreliable for auto-merge)
            if contact.email:
                email_check = supabase.table('identity').select(
                    'person_id'
                ).eq('namespace', 'email').eq('value', contact.email.lower()).execute()

                if email_check.data:
                    existing_person = email_check.data[0]['person_id']

            # NOTE: We no longer auto-merge by name similarity
            # Name matching creates too many false positives (e.g., "Serge" matching "Serge Faguet")
            # Instead, we create new person and log potential duplicates for manual review

            if existing_person:
                if skip_duplicates:
                    duplicates_found += 1
                    skipped += 1
                    details.append({
                        'name': display_name,
                        'status': 'skipped',
                        'reason': 'duplicate'
                    })
                    continue
                else:
                    # Update existing person - add new assertions
                    person_id = existing_person
                    updated += 1
                    is_new = False
            else:
                # Create new person with batch tracking
                person_result = supabase.table('person').insert({
                    'owner_id': user_id,
                    'display_name': display_name,
                    'status': 'active',
                    'import_source': 'linkedin',
                    'import_batch_id': batch_id
                }).execute()

                person_id = person_result.data[0]['person_id']
                new_person_ids.append(person_id)
                is_new = True

                # Check for similar names and log as potential duplicates for review
                # (NOT auto-merge - just record for later review via batch dedup)
                first_name = contact.first_name.strip()
                if first_name and len(first_name) >= 3:  # Only check if first name is meaningful
                    similar_check = supabase.table('person').select(
                        'person_id', 'display_name'
                    ).eq('owner_id', user_id).neq(
                        'person_id', person_id
                    ).ilike(
                        'display_name', f"{first_name}%"  # Starts with first name
                    ).eq('status', 'active').limit(5).execute()

                    if similar_check.data:
                        for similar in similar_check.data:
                            try:
                                supabase.table('person_match_candidate').insert({
                                    'a_person_id': person_id,
                                    'b_person_id': similar['person_id'],
                                    'score': 0.5,  # Low score - just name similarity
                                    'reasons': {
                                        'type': 'name_similarity_on_import',
                                        'new_name': display_name,
                                        'existing_name': similar['display_name'],
                                        'source': 'linkedin'
                                    },
                                    'status': 'pending'
                                }).execute()
                            except Exception:
                                # Ignore duplicate candidate errors
                                pass

            # Create identities
            identities_to_create = [
                {'person_id': person_id, 'namespace': 'linkedin_name', 'value': display_name}
            ]

            if contact.email:
                identities_to_create.append({
                    'person_id': person_id,
                    'namespace': 'email',
                    'value': contact.email.lower()
                })

            for identity in identities_to_create:
                try:
                    supabase.table('identity').insert(identity).execute()
                except Exception:
                    pass  # Ignore duplicate identities

            # Create assertions
            assertions_to_create = []

            if contact.company:
                assertions_to_create.append({
                    'subject_person_id': person_id,
                    'predicate': 'works_at',
                    'object_value': contact.company,
                    'confidence': 0.8,
                    'scope': 'personal'
                })

            if contact.position:
                assertions_to_create.append({
                    'subject_person_id': person_id,
                    'predicate': 'role_is',
                    'object_value': contact.position,
                    'confidence': 0.8,
                    'scope': 'personal'
                })

            if contact.connected_on:
                assertions_to_create.append({
                    'subject_person_id': person_id,
                    'predicate': 'contact_context',
                    'object_value': f"Connected on LinkedIn: {contact.connected_on}",
                    'confidence': 1.0,
                    'scope': 'personal'
                })

            # Generate embeddings and insert assertions
            for assertion in assertions_to_create:
                try:
                    text_for_embedding = f"{assertion['predicate']}: {assertion['object_value']}"
                    embedding = generate_embedding(text_for_embedding)
                    assertion['embedding'] = embedding

                    supabase.table('assertion').insert(assertion).execute()
                except Exception as e:
                    print(f"[IMPORT] Failed to create assertion: {e}")

            if is_new:
                imported += 1
                details.append({
                    'name': display_name,
                    'status': 'imported',
                    'company': contact.company,
                    'position': contact.position
                })
            else:
                details.append({
                    'name': display_name,
                    'status': 'updated',
                    'company': contact.company,
                    'position': contact.position
                })

    except Exception as e:
        # Rollback all changes on any error
        rollback_batch(batch_id, str(e))
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

    # Update batch with final counts
    supabase.table('import_batch').update({
        'new_people': imported,
        'updated_people': updated,
        'duplicates_found': duplicates_found
    }).eq('batch_id', batch_id).execute()

    # Run batch dedup to find potential duplicates with existing contacts
    dedup_result = None
    if imported > 0:
        try:
            dedup_service = get_dedup_service()
            dedup_result = await dedup_service.run_batch_dedup(
                owner_id=UUID(user_id),
                batch_id=batch_id
            )
        except Exception as e:
            print(f"[LINKEDIN IMPORT] Dedup failed: {e}")
            dedup_result = {"error": str(e)}

    # Mark import as complete
    supabase.table('raw_evidence').update({
        'processed': True,
        'processing_status': 'done'
    }).eq('evidence_id', evidence_id).execute()

    # Send Telegram notification
    try:
        proactive_service = get_proactive_service()
        await proactive_service.send_import_report(
            user_id=user_id,
            import_type='linkedin',
            batch_id=batch_id,
            new_people=imported,
            updated_people=updated,
            analytics=analytics,
            dedup_result=dedup_result
        )
    except Exception as e:
        print(f"[LINKEDIN IMPORT] Failed to send Telegram notification: {e}")

    return ImportResult(
        imported=imported,
        skipped=skipped,
        duplicates_found=duplicates_found,
        updated=updated,
        batch_id=batch_id,
        evidence_id=evidence_id,
        analytics=analytics,
        details=details[:20],
        dedup_result=dedup_result
    )


@router.get("/linkedin/sample-csv")
async def get_sample_csv():
    """
    Return a sample CSV for testing.
    """
    sample = """First Name,Last Name,Email Address,Company,Position,Connected On
John,Doe,john.doe@example.com,Google,Software Engineer,15 Jan 2020
Jane,Smith,jane.smith@example.com,Meta,Product Manager,03 Mar 2019
Alex,Johnson,,Amazon,Senior Developer,22 Jul 2021
"""
    return {"sample": sample}


# ============================================
# Batch Management Endpoints
# ============================================

class BatchInfo(BaseModel):
    batch_id: str
    import_type: str
    status: str
    total_contacts: int
    new_people: int
    updated_people: int
    duplicates_found: int
    analytics: dict
    created_at: str


class BatchListResponse(BaseModel):
    batches: list[BatchInfo]


@router.get("/batches", response_model=BatchListResponse)
async def list_import_batches(
    token_payload: dict = Depends(verify_supabase_token)
):
    """List all import batches for the current user."""
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    result = supabase.table('import_batch').select('*').eq(
        'owner_id', user_id
    ).order('created_at', desc=True).limit(20).execute()

    batches = [
        BatchInfo(
            batch_id=b['batch_id'],
            import_type=b['import_type'],
            status=b['status'],
            total_contacts=b['total_contacts'],
            new_people=b['new_people'],
            updated_people=b['updated_people'],
            duplicates_found=b['duplicates_found'],
            analytics=b['analytics'] or {},
            created_at=b['created_at']
        )
        for b in result.data
    ]

    return BatchListResponse(batches=batches)


class RollbackResult(BaseModel):
    batch_id: str
    rolled_back_count: int
    status: str


@router.post("/batches/{batch_id}/rollback", response_model=RollbackResult)
async def rollback_import_batch(
    batch_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Rollback an import batch.

    Soft-deletes all people created in this batch.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Verify batch exists and belongs to user
    batch_check = supabase.table('import_batch').select('*').eq(
        'batch_id', batch_id
    ).eq('owner_id', user_id).single().execute()

    if not batch_check.data:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch_check.data['status'] == 'rolled_back':
        raise HTTPException(status_code=400, detail="Batch already rolled back")

    # Get people to delete first (need their IDs for identity cleanup)
    people_to_delete = supabase.table('person').select('person_id').eq(
        'import_batch_id', batch_id
    ).eq('status', 'active').execute()

    person_ids = [p['person_id'] for p in people_to_delete.data] if people_to_delete.data else []
    rolled_back_count = len(person_ids)

    if person_ids:
        # Delete identities first (they reference person_id)
        supabase.table('identity').delete().in_('person_id', person_ids).execute()

        # Soft delete all people from this batch
        supabase.table('person').update({
            'status': 'deleted'
        }).in_('person_id', person_ids).execute()

    # Mark batch as rolled back
    supabase.table('import_batch').update({
        'status': 'rolled_back',
        'rolled_back_at': 'now()'
    }).eq('batch_id', batch_id).execute()

    return RollbackResult(
        batch_id=batch_id,
        rolled_back_count=rolled_back_count,
        status='rolled_back'
    )
