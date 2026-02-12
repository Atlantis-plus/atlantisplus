"""
Tests for URL normalization utilities.
"""

import pytest
from app.utils.normalize import normalize_linkedin_url, extract_linkedin_username


class TestNormalizeLinkedInUrl:
    """Tests for normalize_linkedin_url function."""

    def test_full_url_with_https_www(self):
        """Standard LinkedIn URL format."""
        result = normalize_linkedin_url("https://www.linkedin.com/in/aturilin")
        assert result == "linkedin.com/in/aturilin"

    def test_full_url_with_https_no_www(self):
        """LinkedIn URL without www."""
        result = normalize_linkedin_url("https://linkedin.com/in/johndoe")
        assert result == "linkedin.com/in/johndoe"

    def test_full_url_with_http(self):
        """LinkedIn URL with http protocol."""
        result = normalize_linkedin_url("http://www.linkedin.com/in/johndoe")
        assert result == "linkedin.com/in/johndoe"

    def test_url_without_protocol(self):
        """LinkedIn URL without protocol."""
        result = normalize_linkedin_url("linkedin.com/in/johndoe")
        assert result == "linkedin.com/in/johndoe"

    def test_url_with_www_no_protocol(self):
        """LinkedIn URL with www but no protocol."""
        result = normalize_linkedin_url("www.linkedin.com/in/johndoe")
        assert result == "linkedin.com/in/johndoe"

    def test_url_with_trailing_slash(self):
        """LinkedIn URL with trailing slash."""
        result = normalize_linkedin_url("https://linkedin.com/in/johndoe/")
        assert result == "linkedin.com/in/johndoe"

    def test_url_with_query_params(self):
        """LinkedIn URL with query parameters."""
        result = normalize_linkedin_url("https://linkedin.com/in/johndoe?utm_source=share")
        assert result == "linkedin.com/in/johndoe"

    def test_url_with_fragment(self):
        """LinkedIn URL with fragment."""
        result = normalize_linkedin_url("https://linkedin.com/in/johndoe#experience")
        assert result == "linkedin.com/in/johndoe"

    def test_uppercase_username(self):
        """Username should be normalized to lowercase."""
        result = normalize_linkedin_url("https://linkedin.com/in/JohnDoe")
        assert result == "linkedin.com/in/johndoe"

    def test_username_with_hyphens(self):
        """Username with hyphens."""
        result = normalize_linkedin_url("https://linkedin.com/in/john-doe-123")
        assert result == "linkedin.com/in/john-doe-123"

    def test_just_username(self):
        """Just the username without URL."""
        result = normalize_linkedin_url("aturilin")
        assert result == "linkedin.com/in/aturilin"

    def test_in_path_only(self):
        """Just /in/username path."""
        result = normalize_linkedin_url("/in/johndoe")
        assert result == "linkedin.com/in/johndoe"

    def test_search_url_returns_none(self):
        """Search URLs should return None."""
        result = normalize_linkedin_url(
            "https://www.linkedin.com/search/results/people/?keywords=John%20Doe"
        )
        assert result is None

    def test_search_url_with_keywords(self):
        """Another search URL format."""
        result = normalize_linkedin_url(
            "https://linkedin.com/search/results/all/?keywords=test"
        )
        assert result is None

    def test_empty_string_returns_none(self):
        """Empty string should return None."""
        result = normalize_linkedin_url("")
        assert result is None

    def test_none_returns_none(self):
        """None should return None."""
        result = normalize_linkedin_url(None)
        assert result is None

    def test_company_url_returns_none(self):
        """Company URLs should return None."""
        result = normalize_linkedin_url("https://linkedin.com/company/google")
        assert result is None

    def test_invalid_username_with_special_chars(self):
        """Invalid username with special characters should return None."""
        result = normalize_linkedin_url("john@doe")
        assert result is None

    def test_whitespace_trimmed(self):
        """Whitespace should be trimmed."""
        result = normalize_linkedin_url("  https://linkedin.com/in/johndoe  ")
        assert result == "linkedin.com/in/johndoe"

    def test_pdl_format(self):
        """PDL returns URLs without protocol."""
        result = normalize_linkedin_url("linkedin.com/in/aturilin")
        assert result == "linkedin.com/in/aturilin"


class TestExtractLinkedInUsername:
    """Tests for extract_linkedin_username function."""

    def test_extract_from_full_url(self):
        """Extract username from full URL."""
        result = extract_linkedin_username("https://www.linkedin.com/in/johndoe")
        assert result == "johndoe"

    def test_extract_from_short_url(self):
        """Extract username from short URL."""
        result = extract_linkedin_username("linkedin.com/in/johndoe")
        assert result == "johndoe"

    def test_search_url_returns_none(self):
        """Search URL should return None."""
        result = extract_linkedin_username(
            "https://linkedin.com/search/results/people/?keywords=test"
        )
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
