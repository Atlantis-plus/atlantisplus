"""
People API.

Endpoints for managing people and their identities/contacts.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id

router = APIRouter(prefix="/people", tags=["people"])


class Identity(BaseModel):
    identity_id: str
    namespace: str
    value: str
    verified: bool


class PersonDetail(BaseModel):
    person_id: str
    display_name: str
    summary: Optional[str] = None
    import_source: Optional[str] = None
    created_at: str
    owner_id: str
    is_own: bool
    identities: list[Identity]
    identity_count: int


class PersonListItem(BaseModel):
    person_id: str
    display_name: str
    summary: Optional[str] = None
    import_source: Optional[str] = None
    created_at: str
    owner_id: str
    is_own: bool
    identity_count: int
    has_email: bool


@router.get("/{person_id}", response_model=PersonDetail)
async def get_person(
    person_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get person details with all identities.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Get person
    person_result = supabase.table('person').select(
        'person_id, display_name, summary, import_source, created_at, owner_id'
    ).eq('person_id', person_id).eq('status', 'active').single().execute()

    if not person_result.data:
        raise HTTPException(status_code=404, detail="Person not found")

    person = person_result.data

    # Get identities
    identities_result = supabase.table('identity').select(
        'identity_id, namespace, value, verified'
    ).eq('person_id', person_id).execute()

    identities = [
        Identity(
            identity_id=i['identity_id'],
            namespace=i['namespace'],
            value=i['value'],
            verified=i.get('verified', False)
        )
        for i in identities_result.data or []
    ]

    return PersonDetail(
        person_id=person['person_id'],
        display_name=person['display_name'],
        summary=person.get('summary'),
        import_source=person.get('import_source'),
        created_at=person['created_at'],
        owner_id=person['owner_id'],
        is_own=person['owner_id'] == user_id,
        identities=identities,
        identity_count=len(identities)
    )


@router.get("/{person_id}/identities", response_model=list[Identity])
async def get_person_identities(
    person_id: str,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Get all identities for a person.
    """
    supabase = get_supabase_admin()

    # Verify person exists
    person_check = supabase.table('person').select('person_id').eq(
        'person_id', person_id
    ).eq('status', 'active').execute()

    if not person_check.data:
        raise HTTPException(status_code=404, detail="Person not found")

    # Get identities
    identities_result = supabase.table('identity').select(
        'identity_id, namespace, value, verified'
    ).eq('person_id', person_id).execute()

    return [
        Identity(
            identity_id=i['identity_id'],
            namespace=i['namespace'],
            value=i['value'],
            verified=i.get('verified', False)
        )
        for i in identities_result.data or []
    ]


@router.get("", response_model=list[PersonListItem])
async def list_people(
    import_source: Optional[str] = None,
    has_email: Optional[bool] = None,
    limit: int = 100,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    List all people with identity counts.
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    # Build query
    query = supabase.table('person').select(
        'person_id, display_name, summary, import_source, created_at, owner_id'
    ).eq('status', 'active')

    if import_source:
        query = query.eq('import_source', import_source)

    query = query.order('created_at', desc=True).limit(limit)
    people_result = query.execute()

    if not people_result.data:
        return []

    # Get identity counts for all people
    person_ids = [p['person_id'] for p in people_result.data]

    # Get all identities for these people
    identities_result = supabase.table('identity').select(
        'person_id, namespace'
    ).in_('person_id', person_ids).execute()

    # Count identities per person and check for email
    identity_counts = {}
    has_email_map = {}
    for i in identities_result.data or []:
        pid = i['person_id']
        identity_counts[pid] = identity_counts.get(pid, 0) + 1
        if i['namespace'] == 'email':
            has_email_map[pid] = True

    # Filter by has_email if specified
    result = []
    for p in people_result.data:
        pid = p['person_id']
        person_has_email = has_email_map.get(pid, False)

        if has_email is not None:
            if has_email and not person_has_email:
                continue
            if not has_email and person_has_email:
                continue

        result.append(PersonListItem(
            person_id=pid,
            display_name=p['display_name'],
            summary=p.get('summary'),
            import_source=p.get('import_source'),
            created_at=p['created_at'],
            owner_id=p['owner_id'],
            is_own=p['owner_id'] == user_id,
            identity_count=identity_counts.get(pid, 0),
            has_email=person_has_email
        ))

    return result
