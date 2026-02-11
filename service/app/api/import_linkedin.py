"""
LinkedIn CSV Import API.

Imports connections from LinkedIn CSV export.
Uses background processing for large imports.
"""

import asyncio
import csv
import io
from datetime import datetime
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel

from app.config import get_settings
from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embeddings_batch
from app.services.dedup import get_dedup_service
from app.services.proactive import get_proactive_service
from app.services.import_analytics import calculate_linkedin_analytics

router = APIRouter(prefix="/import", tags=["import"])

# Keep references to background tasks to prevent garbage collection
_background_tasks: set = set()


class LinkedInContact(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    connected_on: Optional[str] = None
    url: Optional[str] = None


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

    Handles different LinkedIn export formats by finding the header row.
    """
    contacts = []

    # Remove BOM if present
    if content.startswith('\ufeff'):
        content = content[1:]

    # Find the header row (contains "First Name" or similar)
    lines = content.split('\n')
    header_idx = 0
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if 'first name' in line_lower or 'firstname' in line_lower:
            header_idx = i
            print(f"[LINKEDIN CSV] Found header at line {i}: {line[:100]}")
            break

    # Skip rows before header
    if header_idx > 0:
        print(f"[LINKEDIN CSV] Skipping {header_idx} rows before header")
        content = '\n'.join(lines[header_idx:])

    # Try to detect encoding and parse
    reader = csv.DictReader(io.StringIO(content))

    # Log headers for debugging
    print(f"[LINKEDIN CSV] Headers: {reader.fieldnames}")

    for row in reader:
        # Log first row for debugging
        if not contacts:
            print(f"[LINKEDIN CSV] First row keys: {list(row.keys())}")
            print(f"[LINKEDIN CSV] First row values: {list(row.values())[:5]}")

        # Handle different possible column names (LinkedIn format varies by language/version)
        first_name = (row.get('First Name') or row.get('first_name') or
                     row.get('Имя') or row.get('FirstName') or '')
        last_name = (row.get('Last Name') or row.get('last_name') or
                    row.get('Фамилия') or row.get('LastName') or '')
        email = (row.get('Email Address') or row.get('email') or row.get('Email') or
                row.get('E-mail Address') or row.get('Адрес электронной почты') or None)
        company = (row.get('Company') or row.get('company') or
                  row.get('Компания') or row.get('Organization') or None)
        position = (row.get('Position') or row.get('position') or row.get('Title') or
                   row.get('Должность') or row.get('Job Title') or None)
        connected_on = (row.get('Connected On') or row.get('connected_on') or
                       row.get('Дата установления связи') or row.get('Connection Date') or None)
        url = (row.get('URL') or row.get('url') or row.get('Profile URL') or
               row.get('LinkedIn URL') or row.get('Ссылка') or row.get('Profile') or None)

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
            connected_on=connected_on.strip() if connected_on else None,
            url=url.strip() if url else None
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
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Read file content
    try:
        content = await file.read()
        file_name = file.filename or 'connections.csv'
        # Try UTF-8 first, then latin-1
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Save to storage for debugging (even on preview)
    debug_path = f"{user_id}/debug/{file_name}"
    try:
        supabase.storage.from_('imports').upload(
            debug_path, content,
            file_options={"content-type": "text/csv", "upsert": "true"}
        )
        print(f"[LINKEDIN PREVIEW] Saved debug file to {debug_path}")
    except Exception as e:
        print(f"[LINKEDIN PREVIEW] Failed to save debug file: {e}")

    # Log first lines for debugging
    lines = text.split('\n')[:5]
    print(f"[LINKEDIN PREVIEW] First 5 lines:")
    for i, line in enumerate(lines):
        print(f"  {i}: {line[:200]}")

    # Parse CSV
    try:
        contacts = parse_linkedin_csv(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not contacts:
        raise HTTPException(status_code=400, detail=f"No contacts found in CSV. Headers detected: check logs")

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


class ImportStartResponse(BaseModel):
    """Response for starting an import (background processing)"""
    evidence_id: str
    batch_id: str
    total_contacts: int
    message: str


@router.post("/linkedin", response_model=ImportStartResponse, status_code=202)
async def import_linkedin_csv(
    file: UploadFile = File(...),
    skip_duplicates: bool = True,
    background_tasks: BackgroundTasks = None,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Import LinkedIn connections from CSV.

    Returns immediately with evidence_id for tracking.
    Processing happens in background - subscribe to raw_evidence for updates.
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

    # Parse CSV first to validate
    try:
        contacts = parse_linkedin_csv(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found in CSV")

    # Calculate analytics
    contacts_for_analytics = [
        {'connected_on': c.connected_on, 'company': c.company, 'email': c.email}
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
            storage_path, content,
            file_options={"content-type": "text/csv"}
        )
    except Exception as e:
        print(f"[LINKEDIN IMPORT] Failed to upload to storage: {e}")

    # Create raw_evidence for progress tracking
    evidence_result = supabase.table('raw_evidence').insert({
        'owner_id': user_id,
        'source_type': 'import',
        'content': f"LinkedIn import: {len(contacts)} contacts",
        'storage_path': storage_path,
        'metadata': {
            'import_type': 'linkedin',
            'batch_id': batch_id,
            'file_name': file_name,
            'file_size': file_size,
            'stats': {'contacts': len(contacts), 'with_email': sum(1 for c in contacts if c.email)}
        },
        'processing_status': 'pending'
    }).execute()
    evidence_id = evidence_result.data[0]['evidence_id']

    # Start background processing (keep reference to prevent GC)
    task = asyncio.create_task(
        process_linkedin_import_background(
            user_id=user_id,
            batch_id=batch_id,
            evidence_id=evidence_id,
            contacts=contacts,
            skip_duplicates=skip_duplicates,
            analytics=analytics
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ImportStartResponse(
        evidence_id=evidence_id,
        batch_id=batch_id,
        total_contacts=len(contacts),
        message=f"Import started. Processing {len(contacts)} contacts in background."
    )


async def process_linkedin_import_background(
    user_id: str,
    batch_id: str,
    evidence_id: str,
    contacts: list[LinkedInContact],
    skip_duplicates: bool,
    analytics: dict
):
    """
    Background task for LinkedIn import.

    Optimizations:
    - Batch duplicate check (1 query instead of N)
    - Batch person INSERT (groups of 100)
    - Batch embeddings (1 API call per 2000)
    - Batch assertion INSERT (groups of 100)
    """
    supabase = get_supabase_admin()

    def update_status(status: str, content: Optional[str] = None, error: Optional[str] = None):
        update_data = {'processing_status': status}
        if content:
            update_data['content'] = content
        if error:
            update_data['error_message'] = error
        supabase.table('raw_evidence').update(update_data).eq('evidence_id', evidence_id).execute()

    def rollback_batch(error_msg: str):
        try:
            people = supabase.table('person').select('person_id').eq('import_batch_id', batch_id).execute()
            person_ids = [p['person_id'] for p in people.data] if people.data else []
            if person_ids:
                supabase.table('identity').delete().in_('person_id', person_ids).execute()
                supabase.table('assertion').delete().in_('subject_person_id', person_ids).execute()
                supabase.table('person').delete().in_('person_id', person_ids).execute()
            supabase.table('import_batch').update({'status': 'rolled_back'}).eq('batch_id', batch_id).execute()
            update_status('error', error=error_msg)
        except Exception as e:
            print(f"[LINKEDIN IMPORT] Rollback failed: {e}")

    try:
        update_status('extracting', content=f"Checking duplicates...")

        # PHASE 1: Batch check for existing emails
        emails_to_check = [c.email.lower() for c in contacts if c.email]
        existing_emails = set()

        if emails_to_check:
            # Check in batches of 500 (Supabase limit)
            for i in range(0, len(emails_to_check), 500):
                batch_emails = emails_to_check[i:i+500]
                result = supabase.table('identity').select('value').eq(
                    'namespace', 'email'
                ).in_('value', batch_emails).execute()
                existing_emails.update(r['value'] for r in result.data)

        print(f"[LINKEDIN IMPORT] Found {len(existing_emails)} existing emails")

        # PHASE 2: Prepare and batch insert persons
        update_status('extracting', content=f"Creating contacts...")

        imported = 0
        skipped = 0
        duplicates_found = 0

        # Prepare persons for batch insert
        persons_to_create = []
        contact_to_person_idx = {}  # Map contact index to persons_to_create index

        for i, contact in enumerate(contacts):
            display_name = f"{contact.first_name} {contact.last_name}".strip()
            if not display_name:
                skipped += 1
                continue

            # Check if email already exists
            if contact.email and contact.email.lower() in existing_emails:
                if skip_duplicates:
                    duplicates_found += 1
                    skipped += 1
                    continue

            contact_to_person_idx[i] = len(persons_to_create)
            persons_to_create.append({
                'owner_id': user_id,
                'display_name': display_name,
                'status': 'active',
                'import_source': 'linkedin',
                'import_batch_id': batch_id
            })

        print(f"[LINKEDIN IMPORT] Creating {len(persons_to_create)} new persons...")

        # Batch insert persons (groups of 100)
        created_person_ids = []
        for batch_start in range(0, len(persons_to_create), 100):
            batch_chunk = persons_to_create[batch_start:batch_start + 100]
            result = supabase.table('person').insert(batch_chunk).execute()
            created_person_ids.extend(p['person_id'] for p in result.data)

            progress = min(batch_start + 100, len(persons_to_create))
            update_status('extracting', content=f"Created {progress}/{len(persons_to_create)} contacts")

        imported = len(created_person_ids)
        print(f"[LINKEDIN IMPORT] Created {imported} persons")

        # PHASE 3: Collect and batch insert identities
        update_status('extracting', content=f"Adding identities...")

        all_identities = []
        all_assertions = []

        for contact_idx, person_idx in contact_to_person_idx.items():
            contact = contacts[contact_idx]
            person_id = created_person_ids[person_idx]
            display_name = f"{contact.first_name} {contact.last_name}".strip()

            # Use real LinkedIn profile URL if available, otherwise fallback to search URL
            if contact.url:
                linkedin_url = contact.url
            else:
                linkedin_url = f"https://www.linkedin.com/search/results/people/?keywords={quote(display_name, safe='')}"
            all_identities.append({
                'person_id': person_id,
                'namespace': 'linkedin_url',
                'value': linkedin_url
            })

            if contact.email:
                all_identities.append({
                    'person_id': person_id,
                    'namespace': 'email',
                    'value': contact.email.lower()
                })

            if contact.company:
                all_assertions.append({
                    'subject_person_id': person_id,
                    'predicate': 'works_at',
                    'object_value': contact.company,
                    'confidence': 0.8,
                    'scope': 'personal'
                })

            if contact.position:
                all_assertions.append({
                    'subject_person_id': person_id,
                    'predicate': 'role_is',
                    'object_value': contact.position,
                    'confidence': 0.8,
                    'scope': 'personal'
                })

            if contact.connected_on:
                all_assertions.append({
                    'subject_person_id': person_id,
                    'predicate': 'contact_context',
                    'object_value': f"Connected on LinkedIn: {contact.connected_on}",
                    'confidence': 1.0,
                    'scope': 'personal'
                })

        # Batch insert identities
        print(f"[LINKEDIN IMPORT] Inserting {len(all_identities)} identities...")
        for batch_start in range(0, len(all_identities), 100):
            batch_chunk = all_identities[batch_start:batch_start + 100]
            try:
                supabase.table('identity').insert(batch_chunk).execute()
            except Exception:
                # Fallback for duplicates
                for identity in batch_chunk:
                    try:
                        supabase.table('identity').insert(identity).execute()
                    except Exception:
                        pass

        # PHASE 4: Generate embeddings in batch
        update_status('extracting', content=f"Generating embeddings for {len(all_assertions)} facts...")
        print(f"[LINKEDIN IMPORT] Generating embeddings for {len(all_assertions)} assertions...")

        if all_assertions:
            texts = [f"{a['predicate']}: {a['object_value']}" for a in all_assertions]
            all_embeddings = []

            for batch_start in range(0, len(texts), 2000):
                batch_texts = texts[batch_start:batch_start + 2000]
                batch_embeddings = generate_embeddings_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
                print(f"[LINKEDIN IMPORT] Embeddings: {len(all_embeddings)}/{len(texts)}")

            for i, assertion in enumerate(all_assertions):
                assertion['embedding'] = all_embeddings[i]

        # PHASE 5: Batch insert assertions
        update_status('extracting', content=f"Saving {len(all_assertions)} facts...")
        print(f"[LINKEDIN IMPORT] Inserting {len(all_assertions)} assertions...")

        for batch_start in range(0, len(all_assertions), 100):
            batch_chunk = all_assertions[batch_start:batch_start + 100]
            try:
                supabase.table('assertion').insert(batch_chunk).execute()
            except Exception as e:
                print(f"[LINKEDIN IMPORT] Batch assertion insert failed: {e}")
                for assertion in batch_chunk:
                    try:
                        supabase.table('assertion').insert(assertion).execute()
                    except Exception:
                        pass

        # Update batch stats
        supabase.table('import_batch').update({
            'new_people': imported,
            'updated_people': 0,
            'duplicates_found': duplicates_found
        }).eq('batch_id', batch_id).execute()

        # Run dedup
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

        # Mark complete
        supabase.table('raw_evidence').update({
            'processed': True,
            'processing_status': 'done',
            'content': f"LinkedIn import complete: {imported} imported, {duplicates_found} duplicates, {skipped} skipped"
        }).eq('evidence_id', evidence_id).execute()

        # Send notification
        try:
            proactive_service = get_proactive_service()
            await proactive_service.send_import_report(
                user_id=user_id,
                import_type='linkedin',
                batch_id=batch_id,
                new_people=imported,
                updated_people=0,
                analytics=analytics,
                dedup_result=dedup_result
            )
        except Exception as e:
            print(f"[LINKEDIN IMPORT] Notification failed: {e}")

        print(f"[LINKEDIN IMPORT] Complete: {imported} imported, {duplicates_found} duplicates, {skipped} skipped")

    except Exception as e:
        print(f"[LINKEDIN IMPORT] Error: {e}")
        import traceback
        traceback.print_exc()
        rollback_batch(str(e))


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
