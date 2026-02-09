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
    details: list[dict]


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
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()
    dedup_service = get_dedup_service()

    # Read and parse file
    try:
        content = await file.read()
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')
        contacts = parse_linkedin_csv(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found in CSV")

    imported = 0
    skipped = 0
    duplicates_found = 0
    details = []

    for contact in contacts:
        display_name = f"{contact.first_name} {contact.last_name}".strip()

        if not display_name:
            skipped += 1
            continue

        # Check for existing person with same name or email
        existing_person = None

        # Check by email first (more reliable)
        if contact.email:
            email_check = supabase.table('identity').select(
                'person_id'
            ).eq('namespace', 'email').eq('value', contact.email.lower()).execute()

            if email_check.data:
                existing_person = email_check.data[0]['person_id']

        # Check by name if no email match
        if not existing_person:
            name_check = supabase.table('person').select(
                'person_id'
            ).eq('owner_id', user_id).ilike(
                'display_name', f"%{display_name}%"
            ).eq('status', 'active').execute()

            if name_check.data:
                existing_person = name_check.data[0]['person_id']

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
                # Update existing person
                person_id = existing_person
        else:
            # Create new person
            person_result = supabase.table('person').insert({
                'owner_id': user_id,
                'display_name': display_name,
                'status': 'active'
            }).execute()

            person_id = person_result.data[0]['person_id']

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
                # Generate embedding for semantic search
                text_for_embedding = f"{assertion['predicate']}: {assertion['object_value']}"
                embedding = generate_embedding(text_for_embedding)
                assertion['embedding'] = embedding

                supabase.table('assertion').insert(assertion).execute()
            except Exception as e:
                print(f"[IMPORT] Failed to create assertion: {e}")

        imported += 1
        details.append({
            'name': display_name,
            'status': 'imported',
            'company': contact.company,
            'position': contact.position
        })

    return ImportResult(
        imported=imported,
        skipped=skipped,
        duplicates_found=duplicates_found,
        details=details[:20]  # Limit details to first 20
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
