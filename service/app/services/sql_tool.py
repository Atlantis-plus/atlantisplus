"""
Secure SQL Tool for Claude Agent

Provides read-only SQL access with:
1. SELECT-only whitelist (no INSERT/UPDATE/DELETE)
2. Automatic owner_id filtering
3. Statement timeout (5 seconds)
4. Blocked system tables
5. Query validation and sanitization

Usage:
    result = await execute_sql_safe(
        query="SELECT display_name FROM person WHERE status = 'active' LIMIT 10",
        user_id="uuid-here"
    )
"""

import re
from typing import Optional
import json
from dataclasses import dataclass

from app.supabase_client import get_supabase_admin


# =============================================================================
# CONFIGURATION
# =============================================================================

# Tables the agent can query (user data tables only)
ALLOWED_TABLES = {
    'person',
    'assertion',
    'identity',
    'edge',
    'raw_evidence',
    'import_batch',
    'enrichment_job',
    'enrichment_quota',
    'proactive_question',
    'person_match_candidate',
    'chat_session',
    'chat_message',
}

# System tables that must never be accessed
BLOCKED_PATTERNS = [
    r'\bauth\.',           # Supabase auth schema
    r'\bpg_',              # PostgreSQL system
    r'\binformation_schema\.',
    r'\bstorage\.',        # Supabase storage
    r'\brealtime\.',       # Supabase realtime
    r'\bsupabase_',        # Supabase internal
    r'\bextensions\.',     # Extensions schema
    r'\b_',                # Internal tables starting with _
    r'\bpublic\.',         # SECURITY: Block direct schema access (bypasses CTE filter)
]

# Protected CTE names that cannot be redefined by user queries
# These are defined in add_owner_filter() and provide security filtering
PROTECTED_CTE_NAMES = {
    'person', 'assertion', 'identity', 'edge', 'raw_evidence',
    'import_batch', 'enrichment_job', 'enrichment_quota',
    'proactive_question', 'person_match_candidate',
    'chat_session', 'chat_message',
}

# SQL keywords that indicate write operations
WRITE_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE',
    'GRANT', 'REVOKE', 'COPY', 'VACUUM', 'REINDEX', 'CLUSTER',
    'EXECUTE', 'CALL', 'DO', 'SET', 'RESET', 'LOAD', 'REFRESH',
]

# Dangerous functions that could be exploited
BLOCKED_FUNCTIONS = [
    r'\bpg_read_file\b',
    r'\bpg_read_binary_file\b',
    r'\bpg_ls_dir\b',
    r'\blo_import\b',
    r'\blo_export\b',
    r'\bcopy\s+',
    r'\bdblink\b',
    r'\bexec\b',
    r'\bshell\b',
]

# Maximum query execution time in milliseconds
STATEMENT_TIMEOUT_MS = 5000

# Maximum rows to return
MAX_ROWS = 500


# =============================================================================
# TOOL DEFINITION (OpenAI format)
# =============================================================================

SQL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": """Execute a read-only SQL query against the user's network database.

SECURITY: Only SELECT queries allowed. Results automatically filtered to user's data.

AVAILABLE TABLES:
- person (person_id, owner_id, display_name, status, summary, import_source, ...)
- assertion (assertion_id, subject_person_id, predicate, object_value, confidence, ...)
- identity (identity_id, person_id, namespace, value, verified)
- edge (edge_id, src_person_id, dst_person_id, edge_type, weight)
- raw_evidence (evidence_id, owner_id, source_type, content, processed)
- import_batch (batch_id, owner_id, import_type, status, analytics)
- person_match_candidate (a_person_id, b_person_id, score, status)

COMMON PREDICATES (assertion.predicate):
- works_at, role_is - employment
- can_help_with, strong_at - skills
- knows, met_on, contact_context - relationships
- located_in - geography
- background, worked_on - history

IDENTITY NAMESPACES:
- email, phone_hash, linkedin_url, telegram_username, freeform_name

EXAMPLES:
1. Count people by company:
   SELECT object_value as company, COUNT(DISTINCT subject_person_id) as people
   FROM assertion WHERE predicate = 'works_at' GROUP BY object_value ORDER BY people DESC LIMIT 20

2. Find people with specific skill:
   SELECT p.display_name, a.object_value as skill
   FROM person p JOIN assertion a ON p.person_id = a.subject_person_id
   WHERE a.predicate = 'can_help_with' AND a.object_value ILIKE '%AI%'

3. List import sources:
   SELECT import_source, COUNT(*) FROM person WHERE status = 'active' GROUP BY import_source

4. Find contacts with email:
   SELECT p.display_name, i.value as email
   FROM person p JOIN identity i ON p.person_id = i.person_id
   WHERE i.namespace = 'email' LIMIT 10

LIMITATIONS:
- SELECT only (no INSERT/UPDATE/DELETE)
- Max 500 rows returned
- 5 second timeout
- Cannot access auth.users or system tables""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query. Will be automatically filtered to user's data."
                },
                "explain": {
                    "type": "boolean",
                    "description": "If true, returns EXPLAIN output instead of results (for debugging)",
                    "default": False
                }
            },
            "required": ["query"]
        }
    }
}


# =============================================================================
# VALIDATION
# =============================================================================

@dataclass
class ValidationResult:
    """Result of query validation"""
    valid: bool
    error: Optional[str] = None
    sanitized_query: Optional[str] = None


def validate_query(query: str) -> ValidationResult:
    """
    Validate SQL query for safety.

    Returns ValidationResult with:
    - valid: True if query passes all checks
    - error: Description of validation failure
    - sanitized_query: Query with LIMIT added if needed
    """
    if not query or not query.strip():
        return ValidationResult(False, "Empty query")

    # Normalize whitespace and case for checking
    query_normalized = ' '.join(query.split()).upper()
    query_lower = query.lower()

    # 1. Must start with SELECT (or WITH for CTEs)
    if not (query_normalized.startswith('SELECT') or query_normalized.startswith('WITH')):
        return ValidationResult(
            False,
            "Only SELECT queries allowed. Query must start with SELECT or WITH."
        )

    # 2. Check for write keywords
    for keyword in WRITE_KEYWORDS:
        # Use word boundary to avoid false positives like "UPDATED_AT"
        pattern = rf'\b{keyword}\b'
        if re.search(pattern, query_normalized):
            return ValidationResult(
                False,
                f"Write operation '{keyword}' not allowed. Only SELECT queries permitted."
            )

    # 3. Check for blocked system tables
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, query_lower):
            return ValidationResult(
                False,
                f"Access to system tables not allowed. Pattern blocked: {pattern}"
            )

    # 4. Check for dangerous functions
    for pattern in BLOCKED_FUNCTIONS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return ValidationResult(
                False,
                f"Function not allowed for security reasons."
            )

    # 5. Check for comment-based injection attempts
    if '--' in query or '/*' in query:
        return ValidationResult(
            False,
            "SQL comments not allowed."
        )

    # 6. Check for semicolons (multiple statements)
    # Allow one at the end, but not in the middle
    query_stripped = query.strip().rstrip(';')
    if ';' in query_stripped:
        return ValidationResult(
            False,
            "Multiple statements not allowed. Use a single SELECT query."
        )

    # 7. Check for stacked queries via UNION with write
    if 'UNION' in query_normalized:
        # UNION is allowed for SELECT, but check each part
        union_parts = re.split(r'\bUNION\s+(?:ALL\s+)?', query_normalized)
        for part in union_parts:
            part = part.strip()
            if part and not (part.startswith('SELECT') or part.startswith('(')):
                return ValidationResult(
                    False,
                    "Invalid UNION query structure."
                )

    # 8. SECURITY: Check for CTE redefinition attacks
    # User queries cannot redefine our security CTEs (would shadow owner_id filtering)
    cte_pattern = r'\bWITH\s+(\w+)\s+AS\s*\('
    for match in re.finditer(cte_pattern, query, re.IGNORECASE):
        cte_name = match.group(1).lower()
        if cte_name in PROTECTED_CTE_NAMES:
            return ValidationResult(
                False,
                f"Cannot use reserved name '{cte_name}' in WITH clause. "
                f"These names are reserved for security filtering."
            )

    # 9. Ensure LIMIT exists or add it
    sanitized = query_stripped
    if not re.search(r'\bLIMIT\s+\d+', query_normalized):
        sanitized = f"{sanitized} LIMIT {MAX_ROWS}"
    else:
        # Check existing limit is not too high
        limit_match = re.search(r'\bLIMIT\s+(\d+)', query_normalized)
        if limit_match:
            limit_value = int(limit_match.group(1))
            if limit_value > MAX_ROWS:
                # Replace with max allowed
                sanitized = re.sub(
                    r'\bLIMIT\s+\d+',
                    f'LIMIT {MAX_ROWS}',
                    sanitized,
                    flags=re.IGNORECASE
                )

    return ValidationResult(True, None, sanitized)


def add_owner_filter(query: str, user_id: str) -> str:
    """
    Add owner_id filtering to query.

    This is a best-effort addition - it wraps the query in a CTE that
    pre-filters tables by owner_id. For complex queries, RLS in Supabase
    provides the actual security guarantee.

    Note: We use service_role which bypasses RLS, so we must filter manually.
    """
    # Wrap in CTE with filtered views
    wrapped_query = f"""
    WITH
        person AS (
            SELECT * FROM public.person
            WHERE owner_id = '{user_id}'::uuid
        ),
        assertion AS (
            SELECT a.* FROM public.assertion a
            JOIN public.person p ON a.subject_person_id = p.person_id
            WHERE p.owner_id = '{user_id}'::uuid
        ),
        identity AS (
            SELECT i.* FROM public.identity i
            JOIN public.person p ON i.person_id = p.person_id
            WHERE p.owner_id = '{user_id}'::uuid
        ),
        edge AS (
            SELECT e.* FROM public.edge e
            JOIN public.person p ON e.src_person_id = p.person_id
            WHERE p.owner_id = '{user_id}'::uuid
        ),
        raw_evidence AS (
            SELECT * FROM public.raw_evidence
            WHERE owner_id = '{user_id}'::uuid
        ),
        import_batch AS (
            SELECT * FROM public.import_batch
            WHERE owner_id = '{user_id}'::uuid
        ),
        enrichment_job AS (
            SELECT * FROM public.enrichment_job
            WHERE owner_id = '{user_id}'::uuid
        ),
        enrichment_quota AS (
            SELECT * FROM public.enrichment_quota
            WHERE owner_id = '{user_id}'::uuid
        ),
        proactive_question AS (
            SELECT * FROM public.proactive_question
            WHERE owner_id = '{user_id}'::uuid
        ),
        person_match_candidate AS (
            SELECT pmc.* FROM public.person_match_candidate pmc
            JOIN public.person p ON pmc.a_person_id = p.person_id
            WHERE p.owner_id = '{user_id}'::uuid
        ),
        chat_session AS (
            SELECT * FROM public.chat_session
            WHERE owner_id = '{user_id}'::uuid
        ),
        chat_message AS (
            SELECT cm.* FROM public.chat_message cm
            JOIN public.chat_session cs ON cm.session_id = cs.session_id
            WHERE cs.owner_id = '{user_id}'::uuid
        )
    {query}
    """
    return wrapped_query


# =============================================================================
# EXECUTION
# =============================================================================

async def execute_sql_safe(
    query: str,
    user_id: str,
    explain: bool = False
) -> dict:
    """
    Execute a SQL query safely with all security checks.

    Args:
        query: SQL SELECT query
        user_id: UUID of the user (for owner filtering)
        explain: If True, returns EXPLAIN output instead of results

    Returns:
        dict with:
        - success: bool
        - data: list of rows (if success)
        - row_count: number of rows returned
        - error: error message (if failed)
        - query_used: the actual query executed (for debugging)
    """
    # 1. Validate query
    validation = validate_query(query)
    if not validation.valid:
        return {
            "success": False,
            "error": validation.error,
            "data": None,
            "row_count": 0
        }

    safe_query = validation.sanitized_query

    # 2. Add owner filtering via CTE wrapper
    filtered_query = add_owner_filter(safe_query, user_id)

    # 3. Optionally wrap in EXPLAIN
    if explain:
        filtered_query = f"EXPLAIN (FORMAT JSON) {filtered_query}"

    # 4. Execute with timeout
    supabase = get_supabase_admin()

    try:
        # Set statement timeout and execute
        # Note: Supabase Python SDK doesn't support SET directly,
        # so we use a single query with timeout hint via RPC

        # Execute the query
        result = supabase.rpc('execute_readonly_query', {
            'query_text': filtered_query,
            'timeout_ms': STATEMENT_TIMEOUT_MS
        }).execute()

        # RPC returns JSON, parse it
        data = result.data

        return {
            "success": True,
            "data": data if isinstance(data, list) else [data] if data else [],
            "row_count": len(data) if isinstance(data, list) else (1 if data else 0),
            "error": None,
            "query_preview": safe_query[:200] + "..." if len(safe_query) > 200 else safe_query
        }

    except Exception as e:
        error_msg = str(e)

        # Clean up error message for user
        if "timeout" in error_msg.lower():
            error_msg = f"Query timed out after {STATEMENT_TIMEOUT_MS/1000}s. Try a simpler query or add more filters."
        elif "permission denied" in error_msg.lower():
            error_msg = "Permission denied. You can only access your own data."
        elif "does not exist" in error_msg.lower():
            # Extract table/column name from error
            error_msg = f"Table or column not found: {error_msg}"

        return {
            "success": False,
            "error": error_msg,
            "data": None,
            "row_count": 0
        }


# =============================================================================
# ALTERNATIVE: Direct execution without RPC (fallback)
# =============================================================================

async def execute_sql_safe_direct(
    query: str,
    user_id: str,
    explain: bool = False
) -> dict:
    """
    Execute SQL query directly using Supabase's SQL execution.

    This is a fallback if the RPC function doesn't exist.
    Uses Supabase's built-in postgrest execution.
    """
    # 1. Validate
    validation = validate_query(query)
    if not validation.valid:
        return {
            "success": False,
            "error": validation.error,
            "data": None,
            "row_count": 0
        }

    safe_query = validation.sanitized_query
    filtered_query = add_owner_filter(safe_query, user_id)

    if explain:
        filtered_query = f"EXPLAIN (FORMAT TEXT) {filtered_query}"

    # 2. Execute
    supabase = get_supabase_admin()

    try:
        # Use Supabase's SQL execution endpoint
        # This requires the SQL extension to be enabled
        result = supabase.postgrest.rpc(
            'sql',
            {'query': filtered_query}
        ).execute()

        data = result.data

        return {
            "success": True,
            "data": data if isinstance(data, list) else [data] if data else [],
            "row_count": len(data) if isinstance(data, list) else (1 if data else 0),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None,
            "row_count": 0
        }


# =============================================================================
# TOOL EXECUTOR (for integration with chat.py)
# =============================================================================

async def handle_sql_tool(args: dict, user_id: str) -> str:
    """
    Handle SQL tool invocation from Claude agent.

    Args:
        args: Tool arguments (query, explain)
        user_id: User UUID

    Returns:
        JSON string with results
    """
    query = args.get('query', '')
    explain = args.get('explain', False)

    print(f"[SQL_TOOL] Query: {query[:200]}...")

    if not query:
        return json.dumps({
            "success": False,
            "error": "No query provided"
        }, ensure_ascii=False)

    result = await execute_sql_safe(query, user_id, explain)
    print(f"[SQL_TOOL] Result: success={result.get('success')}, rows={result.get('row_count', 0)}, error={result.get('error', 'none')}")

    # Format output for agent consumption
    if result['success']:
        # Truncate if too many rows
        data = result['data']
        if len(data) > 50:
            truncated = data[:50]
            output = {
                "success": True,
                "data": truncated,
                "row_count": result['row_count'],
                "truncated": True,
                "message": f"Showing first 50 of {result['row_count']} rows. Add more specific filters to see all results."
            }
        else:
            output = {
                "success": True,
                "data": data,
                "row_count": result['row_count']
            }
    else:
        output = {
            "success": False,
            "error": result['error']
        }

    return json.dumps(output, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# EXAMPLES FOR TESTING
# =============================================================================

VALID_QUERY_EXAMPLES = [
    # Basic queries
    "SELECT display_name FROM person WHERE status = 'active' LIMIT 10",
    "SELECT COUNT(*) FROM person WHERE status = 'active'",

    # Joins
    """SELECT p.display_name, a.predicate, a.object_value
       FROM person p
       JOIN assertion a ON p.person_id = a.subject_person_id
       WHERE a.predicate = 'works_at'""",

    # Aggregations
    """SELECT a.object_value as company, COUNT(*) as count
       FROM assertion a
       WHERE a.predicate = 'works_at'
       GROUP BY a.object_value
       ORDER BY count DESC
       LIMIT 20""",

    # CTEs
    """WITH tech_people AS (
         SELECT DISTINCT subject_person_id
         FROM assertion
         WHERE object_value ILIKE '%tech%'
       )
       SELECT p.display_name FROM person p
       JOIN tech_people tp ON p.person_id = tp.subject_person_id""",

    # Subqueries
    """SELECT display_name FROM person
       WHERE person_id IN (
         SELECT subject_person_id FROM assertion
         WHERE predicate = 'works_at' AND object_value ILIKE '%Google%'
       )""",
]

INVALID_QUERY_EXAMPLES = [
    # Write operations
    ("INSERT INTO person (display_name) VALUES ('Test')", "Write operation 'INSERT' not allowed"),
    ("UPDATE person SET status = 'deleted'", "Write operation 'UPDATE' not allowed"),
    ("DELETE FROM person WHERE status = 'deleted'", "Write operation 'DELETE' not allowed"),
    ("DROP TABLE person", "Write operation 'DROP' not allowed"),

    # System tables
    ("SELECT * FROM auth.users", "Access to system tables not allowed"),
    ("SELECT * FROM pg_catalog.pg_tables", "Access to system tables not allowed"),
    ("SELECT * FROM information_schema.tables", "Access to system tables not allowed"),

    # SECURITY: Direct schema access (bypasses CTE filter)
    ("SELECT * FROM public.person", "Block direct schema access"),
    ("SELECT * FROM public.assertion WHERE predicate = 'works_at'", "Block direct schema access"),

    # SECURITY: CTE shadowing attack (redefine protected CTEs)
    ("WITH person AS (SELECT * FROM public.person) SELECT * FROM person", "Cannot use reserved name"),
    ("WITH assertion AS (SELECT 1) SELECT * FROM assertion", "Cannot use reserved name"),

    # Multiple statements
    ("SELECT 1; SELECT 2", "Multiple statements not allowed"),
    ("SELECT 1; DROP TABLE person", "Multiple statements not allowed"),

    # Comments (potential injection)
    ("SELECT * FROM person -- WHERE owner_id = 'x'", "SQL comments not allowed"),
    ("SELECT * FROM person /* hidden */", "SQL comments not allowed"),

    # Dangerous functions
    ("SELECT pg_read_file('/etc/passwd')", "Function not allowed"),
]
