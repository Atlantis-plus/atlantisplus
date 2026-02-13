-- Migration: Add normalized company column for better company search
-- This enables grouping of company variants (Yandex, Яндекс, Yandex LLC → yandex)

-- 1. Add normalized column
ALTER TABLE assertion
ADD COLUMN IF NOT EXISTS object_value_normalized TEXT;

-- 2. Create index for fast lookups on company predicates
CREATE INDEX IF NOT EXISTS idx_assertion_normalized
ON assertion(object_value_normalized)
WHERE predicate IN ('works_at', 'met_on') AND object_value_normalized IS NOT NULL;

-- 3. Function to normalize company names
CREATE OR REPLACE FUNCTION normalize_company_name(name TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    result TEXT;
BEGIN
    IF name IS NULL OR trim(name) = '' THEN
        RETURN NULL;
    END IF;

    -- Lowercase and trim
    result := lower(trim(name));

    -- Remove common suffixes (English and some international)
    result := regexp_replace(
        result,
        '\s*(inc\.?|llc\.?|ltd\.?|gmbh|corp\.?|corporation|company|co\.?|limited|plc|ag|sa|nv|n\.v\.)$',
        '',
        'i'
    );

    -- Remove extra whitespace
    result := regexp_replace(result, '\s+', ' ', 'g');

    -- Final trim
    result := trim(result);

    RETURN result;
END;
$$;

-- 4. Backfill existing data for company-related predicates
UPDATE assertion
SET object_value_normalized = normalize_company_name(object_value)
WHERE predicate IN ('works_at', 'met_on', 'worked_on', 'background')
  AND object_value IS NOT NULL
  AND object_value_normalized IS NULL;

-- 5. Create trigger for future inserts/updates
CREATE OR REPLACE FUNCTION trigger_normalize_company()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Only normalize for company-related predicates
    IF NEW.predicate IN ('works_at', 'met_on', 'worked_on', 'background')
       AND NEW.object_value IS NOT NULL THEN
        NEW.object_value_normalized := normalize_company_name(NEW.object_value);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS assertion_normalize_company ON assertion;
CREATE TRIGGER assertion_normalize_company
BEFORE INSERT OR UPDATE OF object_value, predicate ON assertion
FOR EACH ROW
EXECUTE FUNCTION trigger_normalize_company();

-- 6. Add comment for documentation
COMMENT ON COLUMN assertion.object_value_normalized IS
'Normalized company name for grouping variants (lowercase, no suffixes). Auto-filled by trigger for works_at, met_on, worked_on, background predicates.';
