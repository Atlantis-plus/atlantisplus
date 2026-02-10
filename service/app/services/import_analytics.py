"""
Import Analytics Service.

Calculates statistics for imported contacts to show user what was imported.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any


def calculate_linkedin_analytics(contacts: list[dict]) -> dict[str, Any]:
    """
    Calculate analytics for LinkedIn import.

    Args:
        contacts: List of contact dicts with connected_on, company, email, etc.

    Returns:
        Analytics dict with by_year, by_company, with_email counts.
    """
    by_year = defaultdict(int)
    by_company = defaultdict(int)
    with_email = 0
    without_email = 0

    for contact in contacts:
        # Count by year from connected_on
        connected_on = contact.get('connected_on')
        if connected_on:
            try:
                # Try parsing various date formats
                for fmt in ['%d %b %Y', '%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y']:
                    try:
                        dt = datetime.strptime(connected_on.strip(), fmt)
                        by_year[str(dt.year)] += 1
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Count by company
        company = contact.get('company')
        if company and company.strip():
            by_company[company.strip()] += 1

        # Count by email presence
        if contact.get('email'):
            with_email += 1
        else:
            without_email += 1

    # Sort and limit top companies
    top_companies = dict(sorted(
        by_company.items(),
        key=lambda x: -x[1]
    )[:10])

    # Sort years
    sorted_years = dict(sorted(by_year.items(), reverse=True))

    return {
        "by_year": sorted_years,
        "by_company": top_companies,
        "with_email": with_email,
        "without_email": without_email,
        "total": len(contacts)
    }


def calculate_calendar_analytics(events: list[dict], attendees: dict[str, dict]) -> dict[str, Any]:
    """
    Calculate analytics for Calendar import.

    Args:
        events: List of event dicts with date, summary, attendees
        attendees: Dict of email -> {name, count} for unique attendees

    Returns:
        Analytics dict with by_frequency, date_range, top_attendees.
    """
    # Count by meeting frequency
    freq_10_plus = 0
    freq_3_to_9 = 0
    freq_1_to_2 = 0

    for email, info in attendees.items():
        count = info.get('count', 0)
        if count >= 10:
            freq_10_plus += 1
        elif count >= 3:
            freq_3_to_9 += 1
        else:
            freq_1_to_2 += 1

    # Calculate date range from events
    dates = []
    for event in events:
        event_date = event.get('date')
        if event_date:
            try:
                # Handle ISO format
                if 'T' in str(event_date):
                    dates.append(event_date[:10])
                else:
                    dates.append(str(event_date)[:10])
            except Exception:
                pass

    date_range = "Unknown"
    if dates:
        sorted_dates = sorted(dates)
        date_range = f"{sorted_dates[0]} to {sorted_dates[-1]}"

    # Collect unique domains
    domains = defaultdict(int)
    for email in attendees.keys():
        if '@' in email:
            domain = email.split('@')[1]
            domains[domain] += 1

    top_domains = dict(sorted(
        domains.items(),
        key=lambda x: -x[1]
    )[:10])

    # Top attendees by meeting count
    top_attendees = sorted(
        [
            {"email": email, "name": info.get("name"), "meetings": info.get("count", 0)}
            for email, info in attendees.items()
        ],
        key=lambda x: -x["meetings"]
    )[:10]

    return {
        "by_frequency": {
            "10+": freq_10_plus,
            "3-9": freq_3_to_9,
            "1-2": freq_1_to_2
        },
        "date_range": date_range,
        "top_domains": top_domains,
        "top_attendees": top_attendees,
        "total_events": len(events),
        "total_people": len(attendees)
    }
