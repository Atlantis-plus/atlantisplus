-- Migration: Normalize LinkedIn URLs to consistent format
--
-- Problem: LinkedIn identities stored in different formats:
-- - "https://www.linkedin.com/in/username" (from CSV import)
-- - "linkedin.com/in/username" (from PDL enrichment)
-- - "https://linkedin.com/in/username" (various formats)
--
-- Solution: Normalize all to "linkedin.com/in/username" format

SET search_path TO public, extensions;

-- Function to normalize LinkedIn URLs
CREATE OR REPLACE FUNCTION normalize_linkedin_url(url TEXT)
RETURNS TEXT AS $$
DECLARE
    username TEXT;
BEGIN
    IF url IS NULL OR url = '' THEN
        RETURN NULL;
    END IF;

    -- Skip search URLs
    IF url LIKE '%/search/%' OR url LIKE '%keywords=%' THEN
        RETURN NULL;
    END IF;

    -- Extract username from /in/username pattern
    username := substring(url FROM '/in/([^/?#]+)');

    IF username IS NULL OR username = '' THEN
        RETURN NULL;
    END IF;

    -- Clean and normalize username
    username := lower(trim(username));

    RETURN 'linkedin.com/in/' || username;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Step 1: Remove invalid/search URL identities first
DELETE FROM identity
WHERE namespace = 'linkedin_url'
  AND (
      value LIKE '%/search/%'
      OR value LIKE '%keywords=%'
      OR normalize_linkedin_url(value) IS NULL
  );

-- Step 2: Delete duplicates BEFORE normalizing
-- Keep the one that's already normalized, or the oldest if neither is normalized
-- This handles the case where we have both "https://linkedin.com/in/user" and "linkedin.com/in/user"
DELETE FROM identity
WHERE identity_id IN (
    SELECT identity_id
    FROM (
        SELECT
            identity_id,
            person_id,
            value,
            normalize_linkedin_url(value) as normalized_value,
            -- Prefer keeping already normalized values (value = normalized)
            -- Otherwise keep the oldest
            ROW_NUMBER() OVER (
                PARTITION BY person_id, normalize_linkedin_url(value)
                ORDER BY
                    CASE WHEN value = normalize_linkedin_url(value) THEN 0 ELSE 1 END,
                    created_at ASC
            ) as rn
        FROM identity
        WHERE namespace = 'linkedin_url'
          AND normalize_linkedin_url(value) IS NOT NULL
    ) ranked
    WHERE rn > 1
);

-- Step 3: Now normalize the remaining identities (no duplicates left)
UPDATE identity
SET value = normalize_linkedin_url(value)
WHERE namespace = 'linkedin_url'
  AND value IS NOT NULL
  AND normalize_linkedin_url(value) IS NOT NULL
  AND value != normalize_linkedin_url(value);

-- Log results (can be viewed in Supabase logs)
DO $$
DECLARE
    remaining_count INT;
BEGIN
    SELECT COUNT(*) INTO remaining_count
    FROM identity
    WHERE namespace = 'linkedin_url';

    RAISE NOTICE 'LinkedIn URL normalization complete. % identities remaining.', remaining_count;
END $$;
