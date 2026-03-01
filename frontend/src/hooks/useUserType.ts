import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../lib/api';
import type { UserInfo } from '../lib/api';

export type UserType = 'atlantis_plus' | 'community_admin' | 'community_member' | 'new_user';

interface UseUserTypeResult {
  userType: UserType | null;
  userInfo: UserInfo | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Hook to get current user type and related info.
 *
 * User types determine which UI to show:
 * - atlantis_plus: Full app (people, search, chat, notes)
 * - community_admin: Full app filtered by community
 * - community_member: Only SelfProfilePage
 * - new_user: Welcome/onboarding
 */
export const useUserType = (): UseUserTypeResult => {
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Track if we've already fetched to prevent duplicate requests
  const hasFetched = useRef(false);

  const fetchUserInfo = useCallback(async () => {
    // Only fetch if we have an access token
    if (!api.hasAccessToken()) {
      console.log('[useUserType] No access token yet, skipping fetch');
      // Keep loading true - we're waiting for token
      return;
    }

    // Prevent duplicate fetches
    if (hasFetched.current) {
      console.log('[useUserType] Already fetched, skipping');
      return;
    }

    console.log('[useUserType] Fetching user info...');
    hasFetched.current = true;
    setError(null);

    try {
      const info = await api.getUserInfo();
      console.log('[useUserType] Got user info:', info.user_type);
      setUserInfo(info);
    } catch (err) {
      console.error('[useUserType] Failed to fetch user info:', err);
      setError(err instanceof Error ? err.message : 'Failed to get user info');
      // Reset flag so retry can work
      hasFetched.current = false;
    } finally {
      setLoading(false);
    }
  }, []);

  // Subscribe to token availability using event-based approach (no polling)
  useEffect(() => {
    // If token is already available, fetch immediately
    if (api.hasAccessToken()) {
      fetchUserInfo();
      return;
    }

    // Otherwise, wait for token to become available
    console.log('[useUserType] Waiting for access token...');
    const unsubscribe = api.onTokenAvailable(() => {
      console.log('[useUserType] Token now available, fetching...');
      fetchUserInfo();
    });

    return unsubscribe;
  }, [fetchUserInfo]);

  // Manual refetch (resets hasFetched flag)
  const refetch = useCallback(async () => {
    hasFetched.current = false;
    setLoading(true);
    await fetchUserInfo();
  }, [fetchUserInfo]);

  return {
    userType: userInfo?.user_type || null,
    userInfo,
    loading,
    error,
    refetch
  };
};
