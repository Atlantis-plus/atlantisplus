-- Add 'system' to assertion scope CHECK constraint
-- This is needed for service predicates like _enriched_at

-- Drop the existing constraint
ALTER TABLE assertion DROP CONSTRAINT IF EXISTS assertion_scope_check;

-- Add new constraint with 'system' scope included
ALTER TABLE assertion ADD CONSTRAINT assertion_scope_check
  CHECK (scope IN ('personal', 'external', 'system'));
