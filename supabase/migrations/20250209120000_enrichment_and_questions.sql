-- Enrichment & Proactive Questions Schema
-- Migration for gap detection, deduplication, and external enrichment

SET search_path TO public, extensions;

-- ============================================
-- 1. pg_trgm extension for fuzzy name matching
-- ============================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================
-- 2. Extend assertion scope to include 'external' data
-- ============================================
-- Drop and recreate constraint to add 'external' option
ALTER TABLE assertion DROP CONSTRAINT IF EXISTS assertion_scope_check;
-- Note: There may not be a named constraint, so we handle it gracefully
DO $$
BEGIN
    -- Try to add constraint (it will succeed if no constraint exists or after drop)
    ALTER TABLE assertion ADD CONSTRAINT assertion_scope_check
        CHECK (scope IN ('personal', 'external'));
EXCEPTION
    WHEN duplicate_object THEN
        NULL; -- Constraint already exists
END $$;

-- ============================================
-- 3. Add enrichment fields to person table
-- ============================================
ALTER TABLE person ADD COLUMN IF NOT EXISTS enrichment_status TEXT DEFAULT 'none';
ALTER TABLE person ADD COLUMN IF NOT EXISTS last_enriched_at TIMESTAMPTZ;

-- Add constraint for enrichment_status
DO $$
BEGIN
    ALTER TABLE person ADD CONSTRAINT person_enrichment_status_check
        CHECK (enrichment_status IN ('none', 'pending', 'processing', 'done', 'error', 'skipped'));
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END $$;

-- ============================================
-- 4. Enrichment job queue
-- ============================================
CREATE TABLE IF NOT EXISTS enrichment_job (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'done', 'error')),
    provider TEXT NOT NULL DEFAULT 'pdl', -- People Data Labs
    request_payload JSONB,
    response_payload JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_enrichment_job_owner ON enrichment_job(owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_enrichment_job_status ON enrichment_job(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_enrichment_job_person ON enrichment_job(person_id);

ALTER TABLE enrichment_job ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own enrichment jobs" ON enrichment_job;
CREATE POLICY "Users see own enrichment jobs" ON enrichment_job
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- 5. Enrichment quota tracking
-- ============================================
CREATE TABLE IF NOT EXISTS enrichment_quota (
    quota_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
    monthly_used INT NOT NULL DEFAULT 0,
    monthly_limit INT NOT NULL DEFAULT 100,
    daily_used INT NOT NULL DEFAULT 0,
    daily_limit INT NOT NULL DEFAULT 5,
    last_daily_reset DATE NOT NULL DEFAULT CURRENT_DATE,
    last_monthly_reset DATE NOT NULL DEFAULT date_trunc('month', CURRENT_DATE)::DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE enrichment_quota ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own quota" ON enrichment_quota;
CREATE POLICY "Users see own quota" ON enrichment_quota
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- 6. Proactive questions table
-- ============================================
CREATE TABLE IF NOT EXISTS proactive_question (
    question_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    person_id UUID REFERENCES person(person_id) ON DELETE CASCADE,
    question_type TEXT NOT NULL CHECK (question_type IN (
        'gap_fill',           -- Missing information about person
        'dedup_confirm',      -- Confirm if two people are the same
        'contact_context',    -- How did you meet?
        'contact_info',       -- How to reach this person?
        'competencies',       -- What are they good at?
        'work_info'           -- Where do they work?
    )),
    question_text TEXT NOT NULL,
    question_text_ru TEXT,    -- Russian version for display
    metadata JSONB DEFAULT '{}', -- Additional context (e.g., candidate_person_id for dedup)
    priority FLOAT NOT NULL DEFAULT 0.5, -- 0-1, higher = more important
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',    -- Not yet shown
        'shown',      -- Shown to user
        'answered',   -- User provided answer
        'dismissed',  -- User dismissed
        'snoozed',    -- User asked to delay
        'expired'     -- Time passed, no longer relevant
    )),
    answer_text TEXT,
    shown_at TIMESTAMPTZ,
    answered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT (now() + interval '7 days')
);

CREATE INDEX IF NOT EXISTS idx_question_owner_status ON proactive_question(owner_id, status);
CREATE INDEX IF NOT EXISTS idx_question_person ON proactive_question(person_id);
CREATE INDEX IF NOT EXISTS idx_question_pending ON proactive_question(owner_id, priority DESC)
    WHERE status = 'pending';

ALTER TABLE proactive_question ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own questions" ON proactive_question;
CREATE POLICY "Users see own questions" ON proactive_question
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- 7. Question rate limiting table
-- ============================================
CREATE TABLE IF NOT EXISTS question_rate_limit (
    rate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
    questions_shown_today INT NOT NULL DEFAULT 0,
    consecutive_dismisses INT NOT NULL DEFAULT 0,
    last_question_at TIMESTAMPTZ,
    paused_until TIMESTAMPTZ,  -- If user dismisses too many, pause questions
    last_daily_reset DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE question_rate_limit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own rate limit" ON question_rate_limit;
CREATE POLICY "Users see own rate limit" ON question_rate_limit
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- 8. Functions for duplicate detection
-- ============================================

-- Find similar names using trigram similarity
CREATE OR REPLACE FUNCTION find_similar_names(
    p_owner_id UUID,
    p_name TEXT,
    p_threshold FLOAT DEFAULT 0.4
)
RETURNS TABLE (
    person_id UUID,
    display_name TEXT,
    similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        p.person_id,
        p.display_name,
        similarity(p.display_name, p_name) as similarity
    FROM person p
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND p.display_name % p_name  -- Uses pg_trgm operator
      AND similarity(p.display_name, p_name) >= p_threshold
    ORDER BY similarity(p.display_name, p_name) DESC
    LIMIT 10;
$$;

-- Find potential duplicate people (comprehensive check)
CREATE OR REPLACE FUNCTION find_similar_people(
    p_owner_id UUID,
    p_person_id UUID,
    p_name_threshold FLOAT DEFAULT 0.5,
    p_embedding_threshold FLOAT DEFAULT 0.85
)
RETURNS TABLE (
    candidate_person_id UUID,
    candidate_name TEXT,
    match_type TEXT,
    match_score FLOAT,
    match_details JSONB
)
LANGUAGE sql STABLE
AS $$
    WITH target AS (
        SELECT
            person_id,
            display_name,
            summary_embedding
        FROM person
        WHERE person_id = p_person_id
    )
    -- Name similarity matches
    SELECT DISTINCT ON (p.person_id)
        p.person_id as candidate_person_id,
        p.display_name as candidate_name,
        'name_similarity' as match_type,
        similarity(p.display_name, t.display_name) as match_score,
        jsonb_build_object(
            'target_name', t.display_name,
            'candidate_name', p.display_name
        ) as match_details
    FROM person p
    CROSS JOIN target t
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND p.person_id != t.person_id
      AND p.display_name % t.display_name
      AND similarity(p.display_name, t.display_name) >= p_name_threshold

    UNION ALL

    -- Identity matches (exact email, telegram, linkedin)
    SELECT DISTINCT ON (i2.person_id)
        i2.person_id as candidate_person_id,
        p2.display_name as candidate_name,
        'identity_match' as match_type,
        1.0 as match_score,
        jsonb_build_object(
            'namespace', i1.namespace,
            'value', i1.value
        ) as match_details
    FROM identity i1
    JOIN identity i2 ON i1.namespace = i2.namespace
                     AND i1.value = i2.value
                     AND i1.person_id != i2.person_id
    JOIN person p1 ON i1.person_id = p1.person_id
    JOIN person p2 ON i2.person_id = p2.person_id
    WHERE p1.owner_id = p_owner_id
      AND p2.owner_id = p_owner_id
      AND p1.person_id = p_person_id
      AND p2.status = 'active'

    UNION ALL

    -- Embedding similarity (if both have embeddings)
    SELECT DISTINCT ON (p.person_id)
        p.person_id as candidate_person_id,
        p.display_name as candidate_name,
        'embedding_similarity' as match_type,
        1 - (p.summary_embedding <=> t.summary_embedding) as match_score,
        jsonb_build_object(
            'similarity', 1 - (p.summary_embedding <=> t.summary_embedding)
        ) as match_details
    FROM person p
    CROSS JOIN target t
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      AND p.person_id != t.person_id
      AND p.summary_embedding IS NOT NULL
      AND t.summary_embedding IS NOT NULL
      AND 1 - (p.summary_embedding <=> t.summary_embedding) >= p_embedding_threshold

    ORDER BY match_score DESC
    LIMIT 20;
$$;

-- ============================================
-- 9. Calculate profile completeness
-- ============================================
CREATE OR REPLACE FUNCTION calculate_profile_completeness(p_person_id UUID)
RETURNS TABLE (
    completeness_score FLOAT,
    has_contact_context BOOLEAN,
    has_contact_info BOOLEAN,
    has_competencies BOOLEAN,
    has_work_info BOOLEAN,
    has_location BOOLEAN,
    total_assertions INT,
    missing_fields TEXT[]
)
LANGUAGE sql STABLE
AS $$
    WITH assertion_flags AS (
        SELECT
            COUNT(*) as total,
            bool_or(predicate IN ('contact_context', 'background', 'knows')) as has_contact_context,
            bool_or(predicate IN ('intro_path') OR
                    (SELECT COUNT(*) FROM identity WHERE person_id = p_person_id) > 0) as has_contact_info,
            bool_or(predicate IN ('can_help_with', 'strong_at', 'interested_in')) as has_competencies,
            bool_or(predicate IN ('works_at', 'role_is', 'worked_on')) as has_work_info,
            bool_or(predicate = 'located_in') as has_location
        FROM assertion
        WHERE subject_person_id = p_person_id
    )
    SELECT
        -- Score: each field worth 20%, max 100%
        (
            CASE WHEN has_contact_context THEN 0.25 ELSE 0 END +
            CASE WHEN has_contact_info THEN 0.20 ELSE 0 END +
            CASE WHEN has_competencies THEN 0.25 ELSE 0 END +
            CASE WHEN has_work_info THEN 0.20 ELSE 0 END +
            CASE WHEN has_location THEN 0.10 ELSE 0 END
        ) as completeness_score,
        COALESCE(has_contact_context, false),
        COALESCE(has_contact_info, false),
        COALESCE(has_competencies, false),
        COALESCE(has_work_info, false),
        COALESCE(has_location, false),
        COALESCE(total::int, 0),
        ARRAY(
            SELECT unnest FROM unnest(ARRAY[
                CASE WHEN NOT COALESCE(has_contact_context, false) THEN 'contact_context' END,
                CASE WHEN NOT COALESCE(has_contact_info, false) THEN 'contact_info' END,
                CASE WHEN NOT COALESCE(has_competencies, false) THEN 'competencies' END,
                CASE WHEN NOT COALESCE(has_work_info, false) THEN 'work_info' END,
                CASE WHEN NOT COALESCE(has_location, false) THEN 'location' END
            ]) WHERE unnest IS NOT NULL
        ) as missing_fields
    FROM assertion_flags;
$$;

-- ============================================
-- 10. Add index for name similarity searches
-- ============================================
CREATE INDEX IF NOT EXISTS idx_person_name_trgm ON person
    USING gin (display_name gin_trgm_ops)
    WHERE status = 'active';

-- ============================================
-- 11. Update person_match_candidate with RLS
-- ============================================
ALTER TABLE person_match_candidate ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users see own match candidates" ON person_match_candidate;
CREATE POLICY "Users see own match candidates" ON person_match_candidate
    FOR ALL USING (
        a_person_id IN (SELECT person_id FROM person WHERE owner_id = auth.uid())
    );

-- Add owner_id for easier querying
ALTER TABLE person_match_candidate ADD COLUMN IF NOT EXISTS owner_id UUID;

-- Backfill owner_id from person table
UPDATE person_match_candidate pmc
SET owner_id = p.owner_id
FROM person p
WHERE pmc.a_person_id = p.person_id
  AND pmc.owner_id IS NULL;
