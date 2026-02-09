-- Update profile completeness to include relationship_depth
-- Migration: add relationship_depth to completeness calculation

SET search_path TO public, extensions;

-- Drop the function first (return type changed)
DROP FUNCTION IF EXISTS calculate_profile_completeness(UUID);

-- Recreate with updated logic
CREATE OR REPLACE FUNCTION calculate_profile_completeness(p_person_id UUID)
RETURNS TABLE (
    completeness_score FLOAT,
    has_contact_context BOOLEAN,
    has_relationship_depth BOOLEAN,
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
            -- How do I know them (origin of relationship)
            bool_or(predicate = 'contact_context') as has_contact_context,
            -- What have we done together (relationship depth)
            bool_or(predicate = 'relationship_depth') as has_relationship_depth,
            -- How to reach them
            bool_or(predicate IN ('intro_path') OR
                    (SELECT COUNT(*) FROM identity WHERE person_id = p_person_id) > 0) as has_contact_info,
            -- What they're good at
            bool_or(predicate IN ('can_help_with', 'strong_at', 'interested_in', 'recommend_for')) as has_competencies,
            -- Where they work
            bool_or(predicate IN ('works_at', 'role_is', 'worked_on')) as has_work_info,
            -- Where they live
            bool_or(predicate = 'located_in') as has_location
        FROM assertion
        WHERE subject_person_id = p_person_id
    )
    SELECT
        -- Updated scoring: contact_context and relationship_depth are most important
        (
            CASE WHEN has_contact_context THEN 0.30 ELSE 0 END +
            CASE WHEN has_relationship_depth THEN 0.25 ELSE 0 END +
            CASE WHEN has_contact_info THEN 0.15 ELSE 0 END +
            CASE WHEN has_competencies THEN 0.15 ELSE 0 END +
            CASE WHEN has_work_info THEN 0.10 ELSE 0 END +
            CASE WHEN has_location THEN 0.05 ELSE 0 END
        ) as completeness_score,
        COALESCE(has_contact_context, false),
        COALESCE(has_relationship_depth, false),
        COALESCE(has_contact_info, false),
        COALESCE(has_competencies, false),
        COALESCE(has_work_info, false),
        COALESCE(has_location, false),
        COALESCE(total::int, 0),
        ARRAY(
            SELECT unnest FROM unnest(ARRAY[
                CASE WHEN NOT COALESCE(has_contact_context, false) THEN 'contact_context' END,
                CASE WHEN NOT COALESCE(has_relationship_depth, false) THEN 'relationship_depth' END,
                CASE WHEN NOT COALESCE(has_contact_info, false) THEN 'contact_info' END,
                CASE WHEN NOT COALESCE(has_competencies, false) THEN 'competencies' END,
                CASE WHEN NOT COALESCE(has_work_info, false) THEN 'work_info' END,
                CASE WHEN NOT COALESCE(has_location, false) THEN 'location' END
            ]) WHERE unnest IS NOT NULL
        ) as missing_fields
    FROM assertion_flags;
$$;
