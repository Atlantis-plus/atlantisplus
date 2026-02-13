-- Migration: Optimize match_assertions functions for HNSW index
-- Created: 2026-02-13
--
-- Problem: Original functions had WHERE clause on computed distance that
-- prevented PostgreSQL from using the HNSW index, causing timeouts.
--
-- Solution: Use CTE to first get candidates via ORDER BY + LIMIT (uses HNSW),
-- then filter by threshold in outer query.

-- Set search_path to include extensions schema where pgvector lives
SET search_path TO public, extensions;

-- Community version (searches all users' data)
CREATE OR REPLACE FUNCTION match_assertions_community(
    query_embedding vector(1536),
    match_threshold float,
    match_count int
)
RETURNS TABLE (
    assertion_id uuid,
    subject_person_id uuid,
    predicate text,
    object_value text,
    confidence float,
    similarity float,
    owner_id uuid
)
LANGUAGE sql STABLE
AS $$
    WITH candidates AS (
        -- First: get top N*2 by vector distance (HNSW index used here)
        SELECT
            a.assertion_id,
            a.subject_person_id,
            a.predicate,
            a.object_value,
            a.confidence,
            a.embedding,
            1 - (a.embedding <=> query_embedding) as sim
        FROM assertion a
        WHERE a.embedding IS NOT NULL
        ORDER BY a.embedding <=> query_embedding
        LIMIT match_count * 2  -- Get more candidates than needed
    )
    -- Then: join with person and filter by threshold
    SELECT
        c.assertion_id,
        c.subject_person_id,
        c.predicate,
        c.object_value,
        c.confidence,
        c.sim as similarity,
        p.owner_id
    FROM candidates c
    JOIN person p ON c.subject_person_id = p.person_id
    WHERE p.status = 'active'
      AND c.sim > match_threshold
    ORDER BY c.sim DESC
    LIMIT match_count;
$$;

-- Personal version (searches only user's data)
CREATE OR REPLACE FUNCTION match_assertions(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    p_owner_id uuid
)
RETURNS TABLE (
    assertion_id uuid,
    subject_person_id uuid,
    predicate text,
    object_value text,
    confidence float,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    WITH candidates AS (
        -- First: get top N*2 by vector distance (HNSW index used here)
        SELECT
            a.assertion_id,
            a.subject_person_id,
            a.predicate,
            a.object_value,
            a.confidence,
            1 - (a.embedding <=> query_embedding) as sim
        FROM assertion a
        WHERE a.embedding IS NOT NULL
        ORDER BY a.embedding <=> query_embedding
        LIMIT match_count * 2
    )
    -- Then: join with person and filter by owner + threshold
    SELECT
        c.assertion_id,
        c.subject_person_id,
        c.predicate,
        c.object_value,
        c.confidence,
        c.sim as similarity
    FROM candidates c
    JOIN person p ON c.subject_person_id = p.person_id
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND c.sim > match_threshold
    ORDER BY c.sim DESC
    LIMIT match_count;
$$;

COMMENT ON FUNCTION match_assertions_community IS 'Semantic search across all users - optimized for HNSW index';
COMMENT ON FUNCTION match_assertions IS 'Semantic search for single user - optimized for HNSW index';
