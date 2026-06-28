import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/router";
import { Loader2 } from "lucide-react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabaseClient, isSupabaseConfigured } from "../lib/supabase/client";
import { BARE_ROUTES, ROUTES } from "../lib/routes";

interface AuthContextValue {
  /** True when Supabase env is present; false means the app runs open. */
  configured: boolean;
  /** True while the initial session is being resolved. */
  loading: boolean;
  user: User | null;
  session: Session | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  // When not configured, there is nothing to resolve, so we are never loading.
  const [loading, setLoading] = useState<boolean>(isSupabaseConfigured);

  useEffect(() => {
    if (!isSupabaseConfigured) return;

    let active = true;
    let unsubscribe: (() => void) | undefined;

    (async () => {
      const supabase = await getSupabaseClient();
      if (!supabase || !active) return;

      const { data } = await supabase.auth.getSession();
      if (!active) return;
      setSession(data.session);
      setLoading(false);

      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange((_event, nextSession) => {
        setSession(nextSession);
        setLoading(false);
      });
      unsubscribe = () => subscription.unsubscribe();
    })();

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  const signOut = useCallback(async () => {
    const supabase = await getSupabaseClient();
    await supabase?.auth.signOut();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      configured: isSupabaseConfigured,
      loading,
      user: session?.user ?? null,
      session,
      signOut,
    }),
    [loading, session, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Full-screen spinner used while auth resolves or a redirect is in flight. */
function AuthLoading() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-gray-50"
      role="status"
      aria-label="Loading"
    >
      <Loader2 className="h-6 w-6 animate-spin text-brand-600" aria-hidden />
    </div>
  );
}

/**
 * Client-side route guard. When Supabase is configured, unauthenticated users
 * hitting a protected (non-bare) route are redirected to /login with the
 * intended path preserved in `?redirect=`. When not configured, it is a no-op.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { configured, loading, user } = useAuth();
  const isBare = BARE_ROUTES.has(router.pathname);

  useEffect(() => {
    if (!configured || loading || isBare || user) return;
    const redirect = encodeURIComponent(router.asPath);
    router.replace(`${ROUTES.login}?redirect=${redirect}`);
  }, [configured, loading, isBare, user, router]);

  // Block protected content until auth resolves / redirect completes, to avoid
  // flashing the app shell to signed-out users.
  if (configured && !isBare && (loading || !user)) {
    return <AuthLoading />;
  }

  return <>{children}</>;
}
