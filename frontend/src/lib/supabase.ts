import { createClient } from '@supabase/supabase-js';
import type { SupabaseClient, Session } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase credentials not configured. Using placeholder values.');
}

export const supabase: SupabaseClient = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-key'
);

export const setSupabaseSession = async (accessToken: string, refreshToken: string): Promise<Session | null> => {
  const { data, error } = await supabase.auth.setSession({
    access_token: accessToken,
    refresh_token: refreshToken
  });

  if (error) {
    console.error('Failed to set session:', error);
    return null;
  }

  return data.session;
};

export const getSupabaseSession = async (): Promise<Session | null> => {
  const { data } = await supabase.auth.getSession();
  return data.session;
};

export const signOut = async () => {
  await supabase.auth.signOut();
};
