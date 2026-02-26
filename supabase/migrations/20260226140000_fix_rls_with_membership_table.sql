-- Fix RLS infinite recursion on person table
-- Problem: Policy references person from subquery → infinite recursion → 500 error
-- Solution: Create community_member table for membership lookup (no recursion)

SET search_path TO public, extensions;

-- ============================================
-- 1. CREATE COMMUNITY_MEMBER TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS community_member (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    community_id UUID NOT NULL REFERENCES community(community_id),
    telegram_id BIGINT,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, community_id)
);

CREATE INDEX IF NOT EXISTS idx_community_member_user ON community_member(user_id);
CREATE INDEX IF NOT EXISTS idx_community_member_community ON community_member(community_id);
CREATE INDEX IF NOT EXISTS idx_community_member_telegram ON community_member(telegram_id);

-- ============================================
-- 2. ENABLE RLS ON COMMUNITY_MEMBER
-- ============================================
ALTER TABLE community_member ENABLE ROW LEVEL SECURITY;

-- Users can see their own memberships
DROP POLICY IF EXISTS "Users see own memberships" ON community_member;
CREATE POLICY "Users see own memberships" ON community_member
    FOR SELECT USING (user_id = auth.uid());

-- Service role can manage all memberships (bypasses RLS anyway, but explicit)
DROP POLICY IF EXISTS "Service can manage memberships" ON community_member;
CREATE POLICY "Service can manage memberships" ON community_member
    FOR ALL USING (true);

-- ============================================
-- 3. POPULATE FROM EXISTING PERSON RECORDS
-- ============================================
-- Find person records that have community_id and telegram_id,
-- match them to auth.users by telegram_id, and create membership records
INSERT INTO community_member (user_id, community_id, telegram_id)
SELECT DISTINCT
    u.id as user_id,
    p.community_id,
    p.telegram_id
FROM person p
JOIN auth.users u ON u.raw_user_meta_data->>'telegram_id' = p.telegram_id::text
WHERE p.community_id IS NOT NULL
  AND p.telegram_id IS NOT NULL
  AND p.status = 'active'
ON CONFLICT (user_id, community_id) DO NOTHING;

-- ============================================
-- 4. DROP OLD/RECURSIVE POLICIES
-- ============================================
DROP POLICY IF EXISTS "Users see own people or same community members" ON person;
DROP POLICY IF EXISTS "Users see own people" ON person;
DROP POLICY IF EXISTS "Users create own people" ON person;

-- ============================================
-- 5. CREATE SAFE POLICY USING COMMUNITY_MEMBER TABLE
-- ============================================
-- User can see a person if:
-- 1. They own the record (owner_id = auth.uid())
-- 2. OR they are in the same community (via community_member table lookup)
CREATE POLICY "Users see own people or community members" ON person
    FOR SELECT USING (
        -- Case 1: User owns this person record
        owner_id = auth.uid()
        -- Case 2: User is a member of the same community
        OR (
            community_id IS NOT NULL
            AND community_id IN (
                SELECT cm.community_id
                FROM community_member cm
                WHERE cm.user_id = auth.uid()
            )
        )
    );

-- ============================================
-- VERIFY: Check policies on person table
-- Run after migration:
-- SELECT policyname, cmd, qual FROM pg_policies WHERE tablename = 'person';
-- ============================================
