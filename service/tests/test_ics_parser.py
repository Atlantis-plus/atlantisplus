"""
Test ICS parsing for Google Calendar import.

Run: python -m tests.test_ics_parser path/to/calendar.ics
"""

import sys
from icalendar import Calendar
from datetime import datetime
from collections import defaultdict


def parse_ics(file_path: str):
    """Parse ICS file and extract events with attendees."""

    with open(file_path, 'rb') as f:
        cal = Calendar.from_ical(f.read())

    events_with_attendees = []
    all_attendees = defaultdict(int)  # email -> count of meetings

    for component in cal.walk():
        if component.name == "VEVENT":
            # Basic event info
            summary = str(component.get('summary', ''))
            description = str(component.get('description', ''))
            dtstart = component.get('dtstart')
            dtend = component.get('dtend')
            organizer = component.get('organizer')

            # Parse start date
            start_date = None
            if dtstart:
                dt = dtstart.dt
                if isinstance(dt, datetime):
                    start_date = dt.isoformat()
                else:
                    start_date = dt.isoformat()

            # Parse attendees
            attendees = component.get('attendee')
            attendee_list = []

            if attendees:
                # Can be single or list
                if not isinstance(attendees, list):
                    attendees = [attendees]

                for attendee in attendees:
                    email = str(attendee).replace('mailto:', '').lower()
                    # Get CN (common name) if available
                    cn = attendee.params.get('CN', '') if hasattr(attendee, 'params') else ''

                    attendee_list.append({
                        'email': email,
                        'name': cn
                    })
                    all_attendees[email] += 1

            # Parse organizer
            organizer_email = None
            organizer_name = None
            if organizer:
                organizer_email = str(organizer).replace('mailto:', '').lower()
                organizer_name = organizer.params.get('CN', '') if hasattr(organizer, 'params') else ''

            if attendee_list or organizer:
                events_with_attendees.append({
                    'summary': summary,
                    'description': description[:200] if description else '',
                    'start': start_date,
                    'organizer': {'email': organizer_email, 'name': organizer_name},
                    'attendees': attendee_list
                })

    return events_with_attendees, dict(all_attendees)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tests.test_ics_parser path/to/calendar.ics")
        sys.exit(1)

    file_path = sys.argv[1]
    print(f"\n📅 Parsing: {file_path}\n")

    events, attendees = parse_ics(file_path)

    print(f"📊 Summary:")
    print(f"   Total events with attendees: {len(events)}")
    print(f"   Unique attendees: {len(attendees)}")

    # Top attendees
    print(f"\n👥 Top 10 attendees by meeting count:")
    sorted_attendees = sorted(attendees.items(), key=lambda x: -x[1])[:10]
    for email, count in sorted_attendees:
        print(f"   {count:4d} meetings: {email}")

    # Sample events
    print(f"\n📝 Sample events (first 5 with attendees):")
    for event in events[:5]:
        print(f"\n   📌 {event['summary']}")
        print(f"      Date: {event['start']}")
        if event['organizer']['email']:
            print(f"      Organizer: {event['organizer']['name']} <{event['organizer']['email']}>")
        print(f"      Attendees: {len(event['attendees'])}")
        for att in event['attendees'][:3]:
            print(f"         - {att['name']} <{att['email']}>")
        if len(event['attendees']) > 3:
            print(f"         ... and {len(event['attendees']) - 3} more")


if __name__ == "__main__":
    main()
