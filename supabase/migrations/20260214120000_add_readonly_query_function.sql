-- Migration: Add secure read-only query execution function
-- For SQL tool in Claude agent
--
-- Security features:
-- 1. SET LOCAL statement_timeout (per-transaction)
-- 2. Returns JSON for easy parsing
-- 3. Runs with SECURITY INVOKER (uses caller's permissions)

-- Drop if exists to allow re-running
DROP FUNCTION IF EXISTS execute_readonly_query(TEXT, INTEGER);

CREATE OR REPLACE FUNCTION execute_readonly_query(
    query_text TEXT,
    timeout_ms INTEGER DEFAULT 5000
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER  -- Important: uses caller's RLS, not function owner's
AS $$
DECLARE
    result JSONB;
    start_time TIMESTAMPTZ;
BEGIN
    -- Validate timeout (max 30 seconds)
    IF timeout_ms > 30000 THEN
        timeout_ms := 30000;
    END IF;
    IF timeout_ms < 100 THEN
        timeout_ms := 100;
    END IF;

    -- Set statement timeout for this transaction only
    EXECUTE format('SET LOCAL statement_timeout = %s', timeout_ms);

    start_time := clock_timestamp();

    -- Execute query and convert to JSON
    EXECUTE format('SELECT jsonb_agg(row_to_json(t)) FROM (%s) t', query_text)
    INTO result;

    -- Return empty array if null
    IF result IS NULL THEN
        result := '[]'::JSONB;
    END IF;

    RETURN result;

EXCEPTION
    WHEN query_canceled THEN
        -- Timeout hit
        RAISE EXCEPTION 'Query timed out after % ms', timeout_ms;
    WHEN OTHERS THEN
        -- Re-raise with context
        RAISE EXCEPTION 'Query execution failed: %', SQLERRM;
END;
$$;

-- Grant execute to authenticated users only
GRANT EXECUTE ON FUNCTION execute_readonly_query(TEXT, INTEGER) TO authenticated;

-- Comment for documentation
COMMENT ON FUNCTION execute_readonly_query IS
'Execute a read-only SQL query with timeout protection.
Used by Claude agent SQL tool. Query should be SELECT only.
Returns results as JSONB array. Max timeout 30 seconds.';
