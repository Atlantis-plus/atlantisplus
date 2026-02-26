import { useState, useEffect } from 'react';
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

  const fetchUserInfo = async () => {
    // Only fetch if we have an access token
    if (!api.hasAccessToken()) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const info = await api.getUserInfo();
      setUserInfo(info);
    } catch (err) {
      console.error('[useUserType] Failed to fetch user info:', err);
      setError(err instanceof Error ? err.message : 'Failed to get user info');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUserInfo();
  }, []);

  return {
    userType: userInfo?.user_type || null,
    userInfo,
    loading,
    error,
    refetch: fetchUserInfo
  };
};
