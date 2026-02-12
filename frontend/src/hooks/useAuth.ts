import { useState, useEffect, useCallback } from 'react';
import type { Session } from '@supabase/supabase-js';
import { getTelegramInitData, isTelegramMiniApp } from '../lib/telegram';
import { supabase, setSupabaseSession, getSupabaseSession } from '../lib/supabase';
import { api } from '../lib/api';

interface AuthState {
  session: Session | null;
  loading: boolean;
  error: string | null;
  telegramId: number | null;
  displayName: string | null;
}

export const useAuth = () => {
  const [state, setState] = useState<AuthState>({
    session: null,
    loading: true,
    error: null,
    telegramId: null,
    displayName: null
  });

  const authenticate = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      // Check existing session first
      const existingSession = await getSupabaseSession();
      if (existingSession) {
        api.setAccessToken(existingSession.access_token);
        setState({
          session: existingSession,
          loading: false,
          error: null,
          telegramId: existingSession.user.user_metadata?.telegram_id || null,
          displayName: existingSession.user.user_metadata?.display_name || null
        });
        return;
      }

      // If in Telegram Mini App, authenticate via Telegram
      if (isTelegramMiniApp()) {
        const initData = getTelegramInitData();
        if (!initData) {
          throw new Error('No Telegram init data available');
        }

        const authResponse = await api.authTelegram(initData);

        const session = await setSupabaseSession(
          authResponse.access_token,
          authResponse.refresh_token
        );

        if (!session) {
          throw new Error('Failed to set session');
        }

        api.setAccessToken(authResponse.access_token);

        setState({
          session,
          loading: false,
          error: null,
          telegramId: authResponse.telegram_id,
          displayName: authResponse.display_name
        });
      } else {
        // Not in Telegram Mini App - E2E/dev mode with test auth
        const testSecret = import.meta.env.VITE_TEST_AUTH_SECRET || '';
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

        console.log('[DEV] Test auth mode:', { testSecret: testSecret ? 'set' : 'not set', apiUrl });

        if (testSecret) {
          try {
            console.log('[DEV] Calling test auth endpoint...');
            const response = await fetch(`${apiUrl}/auth/telegram/test`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-Test-Secret': testSecret,
              },
              body: JSON.stringify({
                telegram_id: 999999999,
                username: 'e2e_test_user',
                first_name: 'E2E',
                last_name: 'Test'
              }),
            });

            console.log('[DEV] Response status:', response.status);
            if (response.ok) {
              const authResponse = await response.json();
              console.log('[DEV] Auth response received:', { telegram_id: authResponse.telegram_id, display_name: authResponse.display_name });
              const session = await setSupabaseSession(
                authResponse.access_token,
                authResponse.refresh_token
              );
              console.log('[DEV] setSupabaseSession result:', session ? 'success' : 'null');

              if (session) {
                api.setAccessToken(authResponse.access_token);
                setState({
                  session,
                  loading: false,
                  error: null,
                  telegramId: authResponse.telegram_id,
                  displayName: authResponse.display_name
                });
                return;
              }
            }
          } catch (e) {
            console.error('[DEV] Test auth failed:', e);
          }
        }

        // Fallback if test auth fails or no secret
        setState({
          session: null,
          loading: false,
          error: null,
          telegramId: null,
          displayName: 'Dev User'
        });
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Authentication failed'
      }));
    }
  }, []);

  useEffect(() => {
    authenticate();

    // Listen for auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === 'SIGNED_OUT') {
          setState({
            session: null,
            loading: false,
            error: null,
            telegramId: null,
            displayName: null
          });
        } else if (session) {
          api.setAccessToken(session.access_token);
          setState(prev => ({
            ...prev,
            session,
            loading: false
          }));
        }
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, [authenticate]);

  return {
    ...state,
    isAuthenticated: !!state.session,
    retry: authenticate
  };
};
