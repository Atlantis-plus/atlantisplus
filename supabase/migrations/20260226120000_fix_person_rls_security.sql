-- Fix CRITICAL RLS Security Issue on person table
-- Previous policy allowed ANY user to read ALL person records
-- This migration restricts access to:
-- 1. Records owned by the user (owner_id = auth.uid())
-- 2. Records in communities where the user is also a member (same community_id)

SET search_path TO public, extensions;

-- ============================================
-- DROP INSECURE POLICY
-- ============================================
DROP POLICY IF EXISTS "Users see all people or own by telegram" ON person;

-- Also drop any other SELECT policies that might exist
DROP POLICY IF EXISTS "Users see all people" ON person;
DROP POLICY IF EXISTS "Users see own people" ON person;

-- ============================================
-- CREATE SECURE SELECT POLICY
-- User can see a person if:
-- 1. They own the record (owner_id = auth.uid())
-- 2. OR they are in the same community (their telegram_id has a person
--    record in the same community_id)
-- ============================================
CREATE POLICY "Users see own people or same community members" ON person
    FOR SELECT USING (
        -- Case 1: User owns this person record
        owner_id = auth.uid()
        -- Case 2: User is a member of the same community
        OR (
            community_id IS NOT NULL
            AND community_id IN (
                SELECT p.community_id
                FROM person p
                WHERE p.telegram_id = (auth.jwt() -> 'user_metadata' ->> 'telegram_id')::bigint
                  AND p.community_id IS NOT NULL
                  AND p.status = 'active'
            )
        )
    );

-- ============================================
-- ENSURE INSERT/UPDATE/DELETE POLICIES EXIST
-- Only owner can modify records
-- ============================================

-- Drop and recreate to ensure clean state
DROP POLICY IF EXISTS "Users insert own people" ON person;
DROP POLICY IF EXISTS "Users update own people" ON person;
DROP POLICY IF EXISTS "Users delete own people" ON person;

-- INSERT: only owner can create
CREATE POLICY "Users insert own people" ON person
    FOR INSERT WITH CHECK (owner_id = auth.uid());

-- UPDATE: only owner can modify
CREATE POLICY "Users update own people" ON person
    FOR UPDATE USING (owner_id = auth.uid());

-- DELETE: only owner can delete
CREATE POLICY "Users delete own people" ON person
    FOR DELETE USING (owner_id = auth.uid());

-- ============================================
-- VERIFY: List all policies on person table
-- Run after migration to confirm:
-- SELECT policyname, cmd, qual FROM pg_policies WHERE tablename = 'person';
-- ============================================
