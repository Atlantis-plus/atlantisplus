-- Function for universal people search with all filters applied in SQL
-- This ensures LIMIT is applied AFTER filtering, not before

CREATE OR REPLACE FUNCTION find_people_filtered(
    p_owner_id UUID,
    p_name_regex TEXT DEFAULT NULL,
    p_name_contains TEXT DEFAULT NULL,
    p_email_domain TEXT DEFAULT NULL,
    p_has_email BOOLEAN DEFAULT NULL,
    p_import_source TEXT DEFAULT NULL,
    p_company_contains TEXT DEFAULT NULL,
    p_limit INT DEFAULT 100
)
RETURNS TABLE (
    person_id UUID,
    display_name TEXT,
    import_source TEXT,
    has_email BOOLEAN
)
LANGUAGE sql STABLE
AS $$
    WITH people_with_email AS (
        SELECT DISTINCT i.person_id
        FROM identity i
        WHERE i.namespace = 'email'
    ),
    people_with_company AS (
        SELECT DISTINCT a.subject_person_id as person_id
        FROM assertion a
        WHERE a.predicate = 'works_at'
          AND (p_company_contains IS NULL OR a.object_value ILIKE '%' || p_company_contains || '%')
    ),
    people_with_email_domain AS (
        SELECT DISTINCT i.person_id
        FROM identity i
        WHERE i.namespace = 'email'
          AND i.value ILIKE '%@' || p_email_domain
    )
    SELECT
        p.person_id,
        p.display_name,
        p.import_source,
        EXISTS (SELECT 1 FROM people_with_email e WHERE e.person_id = p.person_id) as has_email
    FROM person p
    WHERE p.owner_id = p_owner_id
      AND p.status = 'active'
      -- Name regex filter (PostgreSQL regex)
      AND (p_name_regex IS NULL OR p.display_name ~ p_name_regex)
      -- Name contains filter (case-insensitive)
      AND (p_name_contains IS NULL OR p.display_name ILIKE '%' || p_name_contains || '%')
      -- Import source filter
      AND (p_import_source IS NULL OR p.import_source = p_import_source)
      -- Email domain filter
      AND (p_email_domain IS NULL OR p.person_id IN (SELECT person_id FROM people_with_email_domain))
      -- Has email filter
      AND (p_has_email IS NULL
           OR (p_has_email = true AND p.person_id IN (SELECT person_id FROM people_with_email))
           OR (p_has_email = false AND p.person_id NOT IN (SELECT person_id FROM people_with_email)))
      -- Company filter
      AND (p_company_contains IS NULL OR p.person_id IN (SELECT person_id FROM people_with_company))
    ORDER BY p.display_name
    LIMIT p_limit;
$$;

-- Grant access
GRANT EXECUTE ON FUNCTION find_people_filtered TO authenticated;
GRANT EXECUTE ON FUNCTION find_people_filtered TO service_role;
