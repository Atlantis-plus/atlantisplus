-- Community Sharing Migration
-- Allows all users to see all people (read-only for others' data)
-- Write operations remain restricted to owner

SET search_path TO public, extensions;

-- ============================================
-- PERSON: All users can SELECT, only owner can modify
-- ============================================
DROP POLICY IF EXISTS "Users see own people" ON person;

-- SELECT: everyone sees all people
CREATE POLICY "Users see all people" ON person
    FOR SELECT USING (true);

-- INSERT: only create for yourself
CREATE POLICY "Users create own people" ON person
    FOR INSERT WITH CHECK (owner_id = auth.uid());

-- UPDATE: only modify your own
CREATE POLICY "Users update own people" ON person
    FOR UPDATE USING (owner_id = auth.uid());

-- DELETE: only delete your own
CREATE POLICY "Users delete own people" ON person
    FOR DELETE USING (owner_id = auth.uid());

-- ============================================
-- IDENTITY: All users can SELECT
-- ============================================
DROP POLICY IF EXISTS "Users see identities of own people" ON identity;

CREATE POLICY "Users see all identities" ON identity
    FOR SELECT USING (true);

CREATE POLICY "Users create identities for own people" ON identity
    FOR INSERT WITH CHECK (
        person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users update identities of own people" ON identity
    FOR UPDATE USING (
        person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users delete identities of own people" ON identity
    FOR DELETE USING (
        person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- ASSERTION: All users can SELECT
-- ============================================
DROP POLICY IF EXISTS "Users see assertions of own people" ON assertion;

CREATE POLICY "Users see all assertions" ON assertion
    FOR SELECT USING (true);

CREATE POLICY "Users create assertions for own people" ON assertion
    FOR INSERT WITH CHECK (
        subject_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users update assertions of own people" ON assertion
    FOR UPDATE USING (
        subject_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users delete assertions of own people" ON assertion
    FOR DELETE USING (
        subject_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- EDGE: All users can SELECT
-- ============================================
DROP POLICY IF EXISTS "Users see edges of own people" ON edge;

CREATE POLICY "Users see all edges" ON edge
    FOR SELECT USING (true);

CREATE POLICY "Users create edges for own people" ON edge
    FOR INSERT WITH CHECK (
        src_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users update edges of own people" ON edge
    FOR UPDATE USING (
        src_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

CREATE POLICY "Users delete edges of own people" ON edge
    FOR DELETE USING (
        src_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- ============================================
-- UPDATED SEARCH FUNCTION: Search across all users (community)
-- ============================================
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
    SELECT
        a.assertion_id,
        a.subject_person_id,
        a.predicate,
        a.object_value,
        a.confidence,
        1 - (a.embedding <=> query_embedding) as similarity,
        p.owner_id
    FROM assertion a
    JOIN person p ON a.subject_person_id = p.person_id
    WHERE p.status = 'active'
      AND a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Keep old function for backwards compatibility but update it
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
    SELECT
        a.assertion_id,
        a.subject_person_id,
        a.predicate,
        a.object_value,
        a.confidence,
        1 - (a.embedding <=> query_embedding) as similarity
    FROM assertion a
    JOIN person p ON a.subject_person_id = p.person_id
    WHERE p.status = 'active'
      AND a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
    ORDER BY a.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ============================================
-- Find similar names across ALL users (community)
-- ============================================
CREATE OR REPLACE FUNCTION find_similar_names_community(
    p_name TEXT,
    p_threshold FLOAT DEFAULT 0.4
)
RETURNS TABLE (
    person_id UUID,
    display_name TEXT,
    similarity FLOAT,
    owner_id UUID
)
LANGUAGE sql STABLE
AS $$
    SELECT
        p.person_id,
        p.display_name,
        similarity(p.display_name, p_name) as similarity,
        p.owner_id
    FROM person p
    WHERE p.status = 'active'
      AND p.display_name % p_name  -- Uses pg_trgm operator
      AND similarity(p.display_name, p_name) >= p_threshold
    ORDER BY similarity(p.display_name, p_name) DESC
    LIMIT 10;
$$;
