-- Pending Join State Migration
-- Stores join conversation state persistently to survive bot redeploys

SET search_path TO public, extensions;

-- ============================================
-- PENDING_JOIN: Persistent state for join flow
-- ============================================
CREATE TABLE IF NOT EXISTS pending_join (
    telegram_id BIGINT PRIMARY KEY,
    community_id UUID NOT NULL REFERENCES community(community_id),
    state TEXT NOT NULL DEFAULT 'awaiting_intro'
        CHECK (state IN ('awaiting_intro', 'awaiting_confirmation', 'awaiting_followup', 'awaiting_community_name', 'awaiting_first_person_clarification')),
    extraction JSONB,           -- Extracted data from LLM
    raw_text TEXT,              -- Original transcribed text
    existing_person_id UUID REFERENCES person(person_id),  -- For edit flow
    is_edit BOOLEAN DEFAULT false,                          -- True if editing existing profile
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pending_join_community ON pending_join(community_id);

-- Auto-cleanup old entries (older than 1 hour)
CREATE INDEX IF NOT EXISTS idx_pending_join_created ON pending_join(created_at);

-- RLS: Service role only (bot uses service role key)
ALTER TABLE pending_join ENABLE ROW LEVEL SECURITY;

-- No public access - only service role can read/write
-- (No policies = service role only via service_role_key)

-- ============================================
-- Trigger: Update updated_at on changes
-- ============================================
CREATE OR REPLACE FUNCTION update_pending_join_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_pending_join_updated_at ON pending_join;
CREATE TRIGGER trigger_pending_join_updated_at
    BEFORE UPDATE ON pending_join
    FOR EACH ROW
    EXECUTE FUNCTION update_pending_join_updated_at();

-- ============================================
-- Function: Cleanup expired pending joins (> 1 hour)
-- Can be called periodically or on each check
-- ============================================
CREATE OR REPLACE FUNCTION cleanup_expired_pending_joins()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM pending_join
    WHERE created_at < now() - INTERVAL '1 hour';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;
