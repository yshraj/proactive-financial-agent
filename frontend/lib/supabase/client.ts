import type { SupabaseClient } from "@supabase/supabase-js";

// Public, browser-safe env. The anon key is designed to be exposed client-side;
// row-level security on the server is what protects data.
export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/**
 * Whether Supabase auth is configured. When false, the app runs unauthenticated
 * (current behaviour) — auth UI degrades gracefully and route guards are inert.
 * This keeps local development and CI working without credentials.
 */
export const isSupabaseConfigured: boolean = Boolean(
  SUPABASE_URL && SUPABASE_ANON_KEY
);

let browserClient: SupabaseClient | null = null;

/**
 * Lazily create a singleton browser client, or null when not configured.
 *
 * The Supabase SDK is imported dynamically so it is code-split into its own
 * chunk and never weighs down the shared bundle — when auth is not configured
 * the SDK is never loaded at all.
 */
export async function getSupabaseClient(): Promise<SupabaseClient | null> {
  if (!isSupabaseConfigured) return null;
  if (!browserClient) {
    const { createBrowserClient } = await import("@supabase/ssr");
    browserClient = createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        autoRefreshToken: true,
        detectSessionInUrl: true,
        persistSession: true,
      },
    });
  }
  return browserClient;
}
