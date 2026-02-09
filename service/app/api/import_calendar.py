"""
Google Calendar ICS Import API.

Imports meetings and attendees from Google Calendar ICS export.
"""

from datetime import datetime
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from icalendar import Calendar

from app.supabase_client import get_supabase_admin
from app.middleware.auth import verify_supabase_token, get_user_id
from app.services.embedding import generate_embedding

router = APIRouter(prefix="/import", tags=["import"])


class CalendarAttendee(BaseModel):
    email: str
    name: Optional[str] = None
    meeting_count: int = 0


class CalendarEvent(BaseModel):
    summary: str
    date: str
    attendee_count: int
    attendees: list[str]  # Just names/emails for preview


class CalendarPreview(BaseModel):
    total_events: int
    events_with_attendees: int
    unique_attendees: int
    date_range: str
    top_attendees: list[CalendarAttendee]
    sample_events: list[CalendarEvent]


class CalendarImportResult(BaseModel):
    imported_people: int
    imported_meetings: int
    skipped_duplicates: int
    updated_existing: int


def parse_ics_file(content: bytes, owner_email: Optional[str] = None) -> tuple[list[dict], dict[str, dict]]:
    """
    Parse ICS file and extract events with attendees.

    Returns:
        - List of events with attendee info
        - Dict of unique attendees (email -> {name, count})
    """
    cal = Calendar.from_ical(content)

    events = []
    attendees_map = defaultdict(lambda: {"name": None, "count": 0, "events": []})

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        # Basic event info
        summary = str(component.get('summary', 'No title'))
        description = str(component.get('description', ''))[:500]
        dtstart = component.get('dtstart')
        organizer = component.get('organizer')

        # Parse start date
        start_date = None
        if dtstart:
            dt = dtstart.dt
            if isinstance(dt, datetime):
                start_date = dt.isoformat()
            else:
                start_date = dt.isoformat() if dt else None

        # Parse attendees
        attendee_list = component.get('attendee')
        event_attendees = []

        if attendee_list:
            if not isinstance(attendee_list, list):
                attendee_list = [attendee_list]

            for attendee in attendee_list:
                email = str(attendee).replace('mailto:', '').lower().strip()

                # Skip group calendars and invalid emails
                if '@group.calendar.google.com' in email:
                    continue
                if '@googlegroups.com' in email:
                    continue
                if not '@' in email:
                    continue

                # Skip owner's own email
                if owner_email and email == owner_email.lower():
                    continue

                # Get CN (common name) if available
                cn = None
                if hasattr(attendee, 'params'):
                    cn = attendee.params.get('CN', '')
                    if cn and cn != email:
                        cn = str(cn)
                    else:
                        cn = None

                event_attendees.append({
                    'email': email,
                    'name': cn
                })

                # Update attendee stats
                if cn and not attendees_map[email]["name"]:
                    attendees_map[email]["name"] = cn
                attendees_map[email]["count"] += 1

        # Parse organizer (if not the owner)
        if organizer:
            org_email = str(organizer).replace('mailto:', '').lower().strip()
            if '@' in org_email and '@group.calendar.google.com' not in org_email:
                if not owner_email or org_email != owner_email.lower():
                    org_name = None
                    if hasattr(organizer, 'params'):
                        org_name = organizer.params.get('CN', '')
                        if org_name and org_name != org_email:
                            org_name = str(org_name)
                        else:
                            org_name = None

                    # Add organizer as attendee if not already there
                    if org_email not in [a['email'] for a in event_attendees]:
                        event_attendees.append({
                            'email': org_email,
                            'name': org_name
                        })

                        if org_name and not attendees_map[org_email]["name"]:
                            attendees_map[org_email]["name"] = org_name
                        attendees_map[org_email]["count"] += 1

        if event_attendees:
            events.append({
                'summary': summary,
                'description': description,
                'date': start_date,
                'attendees': event_attendees
            })

    return events, dict(attendees_map)


@router.post("/calendar/preview", response_model=CalendarPreview)
async def preview_calendar_import(
    file: UploadFile = File(...),
    owner_email: Optional[str] = None,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Preview Google Calendar ICS import.

    Returns stats and sample of events/attendees.
    """
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    try:
        events, attendees = parse_ics_file(content, owner_email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse ICS file: {str(e)}")

    if not events:
        raise HTTPException(status_code=400, detail="No events with attendees found in calendar")

    # Calculate date range
    dates = [e['date'] for e in events if e['date']]
    if dates:
        dates_sorted = sorted(dates)
        date_range = f"{dates_sorted[0][:10]} to {dates_sorted[-1][:10]}"
    else:
        date_range = "Unknown"

    # Top attendees
    top_attendees = sorted(
        [
            CalendarAttendee(
                email=email,
                name=info["name"],
                meeting_count=info["count"]
            )
            for email, info in attendees.items()
        ],
        key=lambda x: -x.meeting_count
    )[:10]

    # Sample events
    sample_events = [
        CalendarEvent(
            summary=e['summary'][:100],
            date=e['date'][:10] if e['date'] else 'Unknown',
            attendee_count=len(e['attendees']),
            attendees=[a['name'] or a['email'] for a in e['attendees'][:3]]
        )
        for e in events[:5]
    ]

    return CalendarPreview(
        total_events=len(events) + (len([c for c in Calendar.from_ical(content).walk() if c.name == "VEVENT"]) - len(events)),
        events_with_attendees=len(events),
        unique_attendees=len(attendees),
        date_range=date_range,
        top_attendees=top_attendees,
        sample_events=sample_events
    )


@router.post("/calendar", response_model=CalendarImportResult)
async def import_calendar(
    file: UploadFile = File(...),
    owner_email: Optional[str] = None,
    token_payload: dict = Depends(verify_supabase_token)
):
    """
    Import Google Calendar events and create person records.

    For each unique attendee:
    - Creates or finds person by email
    - Creates assertions for meeting context
    """
    user_id = get_user_id(token_payload)
    supabase = get_supabase_admin()

    try:
        content = await file.read()
        events, attendees = parse_ics_file(content, owner_email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse ICS: {str(e)}")

    if not events:
        raise HTTPException(status_code=400, detail="No events with attendees found")

    imported_people = 0
    skipped_duplicates = 0
    updated_existing = 0
    imported_meetings = 0

    # Process each unique attendee
    for email, info in attendees.items():
        name = info["name"] or email.split('@')[0].replace('.', ' ').title()

        # Check if person exists by email
        existing = supabase.table('identity').select(
            'person_id'
        ).eq('namespace', 'email').eq('value', email).execute()

        if existing.data:
            # Person exists - add calendar context if new
            person_id = existing.data[0]['person_id']
            updated_existing += 1
        else:
            # Check by name similarity (for people without email in LinkedIn import)
            name_check = supabase.table('person').select(
                'person_id'
            ).eq('owner_id', user_id).ilike(
                'display_name', f"%{name}%"
            ).eq('status', 'active').execute()

            if name_check.data:
                # Found similar name - add email identity
                person_id = name_check.data[0]['person_id']
                try:
                    supabase.table('identity').insert({
                        'person_id': person_id,
                        'namespace': 'email',
                        'value': email
                    }).execute()
                except:
                    pass
                updated_existing += 1
            else:
                # Create new person
                person_result = supabase.table('person').insert({
                    'owner_id': user_id,
                    'display_name': name,
                    'status': 'active'
                }).execute()

                person_id = person_result.data[0]['person_id']

                # Create email identity
                supabase.table('identity').insert({
                    'person_id': person_id,
                    'namespace': 'email',
                    'value': email
                }).execute()

                # Create calendar_name identity
                supabase.table('identity').insert({
                    'person_id': person_id,
                    'namespace': 'calendar_name',
                    'value': name
                }).execute()

                imported_people += 1

        # Find events with this attendee and create meeting assertions
        person_events = [
            e for e in events
            if email in [a['email'] for a in e['attendees']]
        ]

        # Create summary assertion about meeting frequency
        if info["count"] >= 3:
            freq_text = f"Met {info['count']} times in calendar"
            try:
                embedding = generate_embedding(f"meeting frequency: {freq_text}")
                supabase.table('assertion').insert({
                    'subject_person_id': person_id,
                    'predicate': 'contact_context',
                    'object_value': freq_text,
                    'confidence': 1.0,
                    'scope': 'personal',
                    'embedding': embedding
                }).execute()
            except:
                pass

        # Create assertions for notable meetings (first 5)
        for event in person_events[:5]:
            if event['summary'] and event['date']:
                meeting_text = f"Meeting: {event['summary']} on {event['date'][:10]}"
                try:
                    embedding = generate_embedding(f"met_on: {meeting_text}")
                    supabase.table('assertion').insert({
                        'subject_person_id': person_id,
                        'predicate': 'met_on',
                        'object_value': meeting_text,
                        'confidence': 1.0,
                        'scope': 'personal',
                        'embedding': embedding
                    }).execute()
                    imported_meetings += 1
                except Exception as e:
                    print(f"[CALENDAR IMPORT] Failed to create assertion: {e}")

    return CalendarImportResult(
        imported_people=imported_people,
        imported_meetings=imported_meetings,
        skipped_duplicates=skipped_duplicates,
        updated_existing=updated_existing
    )
