-- Migration: Import Batch Tracking
-- Purpose: Track mass imports with analytics and enable rollback

-- ============================================
-- IMPORT BATCH TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS import_batch (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    import_type TEXT NOT NULL CHECK (import_type IN ('linkedin', 'calendar', 'contacts', 'gmail')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rolled_back')),

    -- Counts
    total_contacts INTEGER NOT NULL DEFAULT 0,
    new_people INTEGER NOT NULL DEFAULT 0,
    updated_people INTEGER NOT NULL DEFAULT 0,
    duplicates_found INTEGER NOT NULL DEFAULT 0,

    -- Analytics (JSONB for flexibility)
    -- LinkedIn: {by_year: {2020: 50, 2021: 100}, by_company: {...}, with_email: 300}
    -- Calendar: {by_frequency: {"10+": 15, "3-9": 50, "1-2": 200}, date_range: "2020-2024"}
    analytics JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rolled_back_at TIMESTAMPTZ
);

-- Index for user's batches
CREATE INDEX IF NOT EXISTS idx_import_batch_owner ON import_batch(owner_id, created_at DESC);

-- RLS for import_batch
ALTER TABLE import_batch ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own batches" ON import_batch
    FOR ALL USING (owner_id = auth.uid());

-- ============================================
-- ADD COLUMNS TO PERSON TABLE
-- ============================================

-- Import source tracking
ALTER TABLE person ADD COLUMN IF NOT EXISTS import_source TEXT;

-- Link to import batch for rollback
ALTER TABLE person ADD COLUMN IF NOT EXISTS import_batch_id UUID REFERENCES import_batch(batch_id);

-- Index for batch-based queries (rollback, stats)
CREATE INDEX IF NOT EXISTS idx_person_import_batch ON person(import_batch_id) WHERE import_batch_id IS NOT NULL;

-- Index for source-based queries
CREATE INDEX IF NOT EXISTS idx_person_import_source ON person(import_source) WHERE import_source IS NOT NULL;

-- ============================================
-- FUNCTION: Rollback Import Batch
-- ============================================

CREATE OR REPLACE FUNCTION rollback_import_batch(p_batch_id UUID, p_owner_id UUID)
RETURNS TABLE (rolled_back_count INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    -- Verify batch belongs to user and is active
    IF NOT EXISTS (
        SELECT 1 FROM import_batch
        WHERE batch_id = p_batch_id
          AND owner_id = p_owner_id
          AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'Batch not found, not owned by user, or already rolled back';
    END IF;

    -- Soft delete all people from this batch
    UPDATE person
    SET status = 'deleted'
    WHERE import_batch_id = p_batch_id
      AND status = 'active';

    GET DIAGNOSTICS v_count = ROW_COUNT;

    -- Mark batch as rolled back
    UPDATE import_batch
    SET status = 'rolled_back',
        rolled_back_at = now()
    WHERE batch_id = p_batch_id;

    RETURN QUERY SELECT v_count;
END;
$$;

-- ============================================
-- FUNCTION: Get Import Statistics
-- ============================================

CREATE OR REPLACE FUNCTION get_import_stats(p_owner_id UUID, p_import_source TEXT DEFAULT NULL)
RETURNS TABLE (
    import_source TEXT,
    total_people BIGINT,
    active_people BIGINT,
    batch_count BIGINT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        p.import_source,
        COUNT(*) as total_people,
        COUNT(*) FILTER (WHERE p.status = 'active') as active_people,
        COUNT(DISTINCT p.import_batch_id) as batch_count
    FROM person p
    WHERE p.owner_id = p_owner_id
      AND p.import_source IS NOT NULL
      AND (p_import_source IS NULL OR p.import_source = p_import_source)
    GROUP BY p.import_source
    ORDER BY total_people DESC;
$$;
