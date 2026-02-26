-- Community Intake Mode Migration
-- Adds community table for channel owners to collect member profiles

SET search_path TO public, extensions;

-- ============================================
-- COMMUNITY: Channel/group that collects member profiles
-- ============================================
CREATE TABLE IF NOT EXISTS community (
    community_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    telegram_channel_id BIGINT,
    name TEXT NOT NULL,
    description TEXT,
    invite_code TEXT UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(6), 'hex'),
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_community_owner ON community(owner_id);
CREATE INDEX IF NOT EXISTS idx_community_invite ON community(invite_code) WHERE is_active = true;

-- RLS
ALTER TABLE community ENABLE ROW LEVEL SECURITY;

-- Owner can do everything with their communities
CREATE POLICY "Owner full access" ON community
    FOR ALL USING (owner_id = auth.uid());

-- Anyone can read community info (for join flow)
CREATE POLICY "Public read communities" ON community
    FOR SELECT USING (true);

-- ============================================
-- ATLANTIS_PLUS_MEMBER: Users with full access
-- ============================================
CREATE TABLE IF NOT EXISTS atlantis_plus_member (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    granted_at TIMESTAMPTZ DEFAULT now(),
    granted_by UUID REFERENCES auth.users(id)
);

ALTER TABLE atlantis_plus_member ENABLE ROW LEVEL SECURITY;

-- Everyone can see who is a member (needed for user_type check)
CREATE POLICY "Public read members" ON atlantis_plus_member
    FOR SELECT USING (true);

-- Only existing members can add new members
CREATE POLICY "Members add members" ON atlantis_plus_member
    FOR INSERT WITH CHECK (
        auth.uid() IN (SELECT user_id FROM atlantis_plus_member)
    );

-- ============================================
-- ADD community_id TO PERSON
-- For filtering people by community
-- ============================================
ALTER TABLE person ADD COLUMN IF NOT EXISTS community_id UUID REFERENCES community(community_id);
CREATE INDEX IF NOT EXISTS idx_person_community ON person(community_id) WHERE community_id IS NOT NULL;

-- ============================================
-- ADD telegram_id TO PERSON (for self-profile lookup)
-- Community members find their own profile by telegram_id
-- ============================================
ALTER TABLE person ADD COLUMN IF NOT EXISTS telegram_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_person_telegram ON person(telegram_id) WHERE telegram_id IS NOT NULL;

-- ============================================
-- Update RLS policies to handle community members
-- Community members can READ their own person record by telegram_id
-- ============================================

-- Drop existing SELECT policy to recreate
DROP POLICY IF EXISTS "Users see all people" ON person;

-- New SELECT policy: see all people OR your own by telegram_id
CREATE POLICY "Users see all people or own by telegram" ON person
    FOR SELECT USING (
        -- Regular access via RLS (all active people)
        true
    );

-- Keep INSERT/UPDATE/DELETE policies for owners
-- (Already exist from previous migrations)

-- ============================================
-- Function: Find person by telegram_id + community_id
-- For community member self-profile lookup
-- ============================================
CREATE OR REPLACE FUNCTION find_person_by_telegram(
    p_telegram_id BIGINT,
    p_community_id UUID
)
RETURNS TABLE (
    person_id UUID,
    display_name TEXT,
    summary TEXT,
    created_at TIMESTAMPTZ,
    owner_id UUID,
    community_id UUID
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT
        p.person_id,
        p.display_name,
        p.summary,
        p.created_at,
        p.owner_id,
        p.community_id
    FROM person p
    WHERE p.telegram_id = p_telegram_id
      AND p.community_id = p_community_id
      AND p.status = 'active'
    LIMIT 1;
$$;

-- ============================================
-- Function: Check if user is Atlantis+ member
-- ============================================
CREATE OR REPLACE FUNCTION is_atlantis_plus_member(p_user_id UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT EXISTS (
        SELECT 1 FROM atlantis_plus_member WHERE user_id = p_user_id
    );
$$;

-- ============================================
-- Function: Get communities owned by user
-- ============================================
CREATE OR REPLACE FUNCTION get_communities_by_owner(p_user_id UUID)
RETURNS TABLE (
    community_id UUID,
    name TEXT,
    invite_code TEXT,
    is_active BOOLEAN,
    created_at TIMESTAMPTZ
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT
        c.community_id,
        c.name,
        c.invite_code,
        c.is_active,
        c.created_at
    FROM community c
    WHERE c.owner_id = p_user_id
      AND c.is_active = true
    ORDER BY c.created_at DESC;
$$;

-- ============================================
-- Function: Get communities where user is a member (by telegram_id)
-- ============================================
CREATE OR REPLACE FUNCTION get_communities_by_member_telegram(p_telegram_id BIGINT)
RETURNS TABLE (
    community_id UUID,
    name TEXT,
    person_id UUID,
    created_at TIMESTAMPTZ
)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
    SELECT
        c.community_id,
        c.name,
        p.person_id,
        p.created_at
    FROM person p
    JOIN community c ON p.community_id = c.community_id
    WHERE p.telegram_id = p_telegram_id
      AND p.status = 'active'
      AND c.is_active = true
    ORDER BY p.created_at DESC;
$$;

-- ============================================
-- Trigger: Update community.updated_at on changes
-- ============================================
CREATE OR REPLACE FUNCTION update_community_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_community_updated_at ON community;
CREATE TRIGGER trigger_community_updated_at
    BEFORE UPDATE ON community
    FOR EACH ROW
    EXECUTE FUNCTION update_community_updated_at();
