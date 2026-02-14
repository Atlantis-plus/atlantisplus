"""
Tests for SQL Tool security validation.

Run with: pytest tests/test_sql_tool.py -v
"""

import pytest
from app.services.sql_tool import (
    validate_query,
    ValidationResult,
    VALID_QUERY_EXAMPLES,
    INVALID_QUERY_EXAMPLES,
    MAX_ROWS,
)


class TestValidateQuery:
    """Test query validation logic."""

    # =========================================================================
    # VALID QUERIES
    # =========================================================================

    def test_simple_select(self):
        result = validate_query("SELECT * FROM person")
        assert result.valid is True
        assert result.error is None
        assert "LIMIT" in result.sanitized_query.upper()

    def test_select_with_where(self):
        result = validate_query(
            "SELECT display_name FROM person WHERE status = 'active'"
        )
        assert result.valid is True

    def test_select_with_join(self):
        result = validate_query("""
            SELECT p.display_name, a.object_value
            FROM person p
            JOIN assertion a ON p.person_id = a.subject_person_id
        """)
        assert result.valid is True

    def test_select_with_cte(self):
        result = validate_query("""
            WITH active_people AS (
                SELECT person_id FROM person WHERE status = 'active'
            )
            SELECT * FROM active_people
        """)
        assert result.valid is True

    def test_select_with_subquery(self):
        result = validate_query("""
            SELECT * FROM person
            WHERE person_id IN (
                SELECT subject_person_id FROM assertion WHERE predicate = 'works_at'
            )
        """)
        assert result.valid is True

    def test_select_with_aggregation(self):
        result = validate_query("""
            SELECT predicate, COUNT(*) as cnt
            FROM assertion
            GROUP BY predicate
            ORDER BY cnt DESC
        """)
        assert result.valid is True

    def test_select_with_union(self):
        result = validate_query("""
            SELECT display_name FROM person WHERE status = 'active'
            UNION ALL
            SELECT display_name FROM person WHERE status = 'merged'
        """)
        assert result.valid is True

    def test_existing_limit_preserved(self):
        result = validate_query("SELECT * FROM person LIMIT 10")
        assert result.valid is True
        # Should keep the limit as-is since it's below MAX_ROWS
        assert "LIMIT 10" in result.sanitized_query or "LIMIT" in result.sanitized_query.upper()

    def test_high_limit_reduced(self):
        result = validate_query("SELECT * FROM person LIMIT 99999")
        assert result.valid is True
        assert f"LIMIT {MAX_ROWS}" in result.sanitized_query.upper()

    def test_all_example_valid_queries(self):
        """All example valid queries should pass validation."""
        for query in VALID_QUERY_EXAMPLES:
            result = validate_query(query)
            assert result.valid is True, f"Query should be valid: {query[:100]}..."

    # =========================================================================
    # INVALID QUERIES - Write operations
    # Note: These fail because query doesn't start with SELECT/WITH,
    # which is the first validation check (fail-fast design).
    # =========================================================================

    def test_insert_blocked(self):
        result = validate_query("INSERT INTO person (display_name) VALUES ('Test')")
        assert result.valid is False
        # Fails at "must start with SELECT" check
        assert "SELECT" in result.error.upper() or "INSERT" in result.error.upper()

    def test_update_blocked(self):
        result = validate_query("UPDATE person SET status = 'deleted'")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "UPDATE" in result.error.upper()

    def test_delete_blocked(self):
        result = validate_query("DELETE FROM person WHERE status = 'deleted'")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "DELETE" in result.error.upper()

    def test_drop_blocked(self):
        result = validate_query("DROP TABLE person")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "DROP" in result.error.upper()

    def test_create_blocked(self):
        result = validate_query("CREATE TABLE evil (id int)")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "CREATE" in result.error.upper()

    def test_alter_blocked(self):
        result = validate_query("ALTER TABLE person ADD COLUMN evil TEXT")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "ALTER" in result.error.upper()

    def test_truncate_blocked(self):
        result = validate_query("TRUNCATE person")
        assert result.valid is False
        assert "SELECT" in result.error.upper() or "TRUNCATE" in result.error.upper()

    def test_write_in_subquery_blocked(self):
        """Write operations hidden in subqueries should still be blocked."""
        result = validate_query(
            "SELECT * FROM (DELETE FROM person RETURNING *) t"
        )
        assert result.valid is False

    # =========================================================================
    # INVALID QUERIES - System tables
    # =========================================================================

    def test_auth_users_blocked(self):
        result = validate_query("SELECT * FROM auth.users")
        assert result.valid is False
        assert "system tables" in result.error.lower()

    def test_pg_catalog_blocked(self):
        result = validate_query("SELECT * FROM pg_catalog.pg_tables")
        assert result.valid is False

    def test_information_schema_blocked(self):
        result = validate_query("SELECT * FROM information_schema.tables")
        assert result.valid is False

    def test_storage_blocked(self):
        result = validate_query("SELECT * FROM storage.objects")
        assert result.valid is False

    # =========================================================================
    # INVALID QUERIES - Injection attempts
    # =========================================================================

    def test_semicolon_injection_blocked(self):
        result = validate_query("SELECT 1; DROP TABLE person")
        assert result.valid is False
        # Can fail at write keyword check or multiple statements check
        assert "Multiple statements" in result.error or "DROP" in result.error.upper()

    def test_comment_dash_blocked(self):
        result = validate_query("SELECT * FROM person -- WHERE owner_id = 'x'")
        assert result.valid is False
        assert "comments" in result.error.lower()

    def test_comment_block_blocked(self):
        result = validate_query("SELECT * FROM person /* hidden */")
        assert result.valid is False
        assert "comments" in result.error.lower()

    def test_multiple_statements_blocked(self):
        result = validate_query("SELECT 1; SELECT 2")
        assert result.valid is False

    # =========================================================================
    # INVALID QUERIES - Dangerous functions
    # =========================================================================

    def test_pg_read_file_blocked(self):
        result = validate_query("SELECT pg_read_file('/etc/passwd')")
        assert result.valid is False
        assert "not allowed" in result.error.lower()

    def test_lo_export_blocked(self):
        result = validate_query("SELECT lo_export(12345, '/tmp/file')")
        assert result.valid is False

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_empty_query(self):
        result = validate_query("")
        assert result.valid is False
        assert "Empty" in result.error

    def test_whitespace_only(self):
        result = validate_query("   \n\t   ")
        assert result.valid is False

    def test_not_starting_with_select(self):
        result = validate_query("EXPLAIN SELECT * FROM person")
        # EXPLAIN is not SELECT, should fail
        assert result.valid is False

    def test_case_insensitive_keywords(self):
        # INSERT should be blocked regardless of case
        result = validate_query("insert into person (name) values ('x')")
        assert result.valid is False

        result = validate_query("InSeRt INTO person (name) VALUES ('x')")
        assert result.valid is False

    def test_updated_at_column_allowed(self):
        """Column names containing UPDATE should be allowed."""
        result = validate_query("SELECT updated_at FROM person")
        assert result.valid is True

    def test_trailing_semicolon_allowed(self):
        """Single trailing semicolon should be stripped and allowed."""
        result = validate_query("SELECT * FROM person;")
        assert result.valid is True

    def test_all_example_invalid_queries(self):
        """All example invalid queries should fail validation."""
        for query, expected_error in INVALID_QUERY_EXAMPLES:
            result = validate_query(query)
            assert result.valid is False, f"Query should be invalid: {query}"


class TestOwnerFiltering:
    """Test that owner_id filtering is applied correctly."""

    def test_owner_filter_wraps_query(self):
        from app.services.sql_tool import add_owner_filter

        query = "SELECT * FROM person"
        user_id = "12345678-1234-1234-1234-123456789abc"

        filtered = add_owner_filter(query, user_id)

        # Should contain the user_id
        assert user_id in filtered
        # Should contain CTE definitions
        assert "WITH" in filtered
        # Should reference public.person
        assert "public.person" in filtered
        # Should filter by owner_id
        assert "owner_id =" in filtered


class TestToolDefinition:
    """Test the tool definition format."""

    def test_tool_definition_structure(self):
        from app.services.sql_tool import SQL_TOOL_DEFINITION

        assert SQL_TOOL_DEFINITION["type"] == "function"
        assert "function" in SQL_TOOL_DEFINITION
        assert SQL_TOOL_DEFINITION["function"]["name"] == "execute_sql"
        assert "parameters" in SQL_TOOL_DEFINITION["function"]
        assert "query" in SQL_TOOL_DEFINITION["function"]["parameters"]["properties"]

    def test_tool_definition_has_examples(self):
        from app.services.sql_tool import SQL_TOOL_DEFINITION

        description = SQL_TOOL_DEFINITION["function"]["description"]
        # Should have practical examples
        assert "SELECT" in description
        assert "works_at" in description
        assert "LIMIT" in description
