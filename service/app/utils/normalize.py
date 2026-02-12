"""
URL normalization utilities.

Ensures consistent format for identifiers across different sources.
"""

import re
from typing import Optional
from urllib.parse import urlparse


def normalize_linkedin_url(value: str) -> Optional[str]:
    """
    Normalize LinkedIn URL to consistent format.

    Input formats handled:
    - "https://www.linkedin.com/in/username"
    - "https://linkedin.com/in/username"
    - "http://www.linkedin.com/in/username"
    - "www.linkedin.com/in/username"
    - "linkedin.com/in/username"
    - "/in/username"
    - "username" (just the username)

    Output format: "linkedin.com/in/username" (no protocol, no www)

    Returns None if the value doesn't look like a valid LinkedIn profile.
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()

    # Skip search URLs — they're not real profile URLs
    if "/search/" in value or "keywords=" in value:
        return None

    # Extract username from various formats
    username = None

    # Try parsing as URL first
    if "linkedin.com" in value.lower() or value.startswith("http"):
        # Add protocol if missing for proper parsing
        if not value.startswith("http"):
            value = "https://" + value

        parsed = urlparse(value)
        path = parsed.path

        # Look for /in/username pattern
        match = re.search(r'/in/([^/?#]+)', path)
        if match:
            username = match.group(1)
    elif value.startswith("/in/"):
        # Handle "/in/username" format
        username = value[4:].split("/")[0].split("?")[0]
    elif "/" not in value and "@" not in value and len(value) > 0:
        # Assume it's just a username
        username = value

    if not username:
        return None

    # Clean up username
    username = username.strip().lower()

    # Basic validation: LinkedIn usernames are alphanumeric with hyphens
    if not re.match(r'^[a-z0-9-]+$', username):
        return None

    return f"linkedin.com/in/{username}"


def extract_linkedin_username(value: str) -> Optional[str]:
    """
    Extract just the username from LinkedIn URL.

    Returns None if not a valid LinkedIn URL.
    """
    normalized = normalize_linkedin_url(value)
    if normalized:
        return normalized.split("/in/")[1]
    return None
