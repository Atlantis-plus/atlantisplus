-- Bug #7 fix: Prevent duplicate profiles for same telegram_id + community_id
-- Uses partial unique index (only for active profiles with non-null values)

SET search_path TO public, extensions;

-- Create partial unique index to prevent duplicates
-- Only applies to active profiles with non-null telegram_id and community_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_unique_telegram_community
    ON person (telegram_id, community_id)
    WHERE telegram_id IS NOT NULL
      AND community_id IS NOT NULL
      AND status = 'active';

-- Note: This is a partial index, not a table constraint, because:
-- 1. We only want uniqueness for active profiles (deleted ones can have duplicates)
-- 2. We only want uniqueness when both telegram_id AND community_id are set
-- 3. Regular person records (not community profiles) don't have community_id

COMMENT ON INDEX idx_person_unique_telegram_community IS
    'Prevents duplicate community profiles: one active profile per telegram user per community';
