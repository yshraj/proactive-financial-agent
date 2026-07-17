import Head from "next/head";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { AuthShell } from "../components/AuthShell";
import { Button, useToast } from "../components/ui";
import { getSupabaseClient, isSupabaseConfigured } from "../lib/supabase/client";
import { APP_ENTRY } from "../lib/routes";

/**
 * Landing page for the Supabase recovery link. Supabase establishes a session
 * from the link's token (PASSWORD_RECOVERY event); the user then sets a new
 * password via updateUser.
 */
export default function ResetPasswordPage() {
  const router = useRouter();
  const { notify } = useToast();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isSupabaseConfigured) return;
    let unsubscribe: (() => void) | undefined;
    (async () => {
      const supabase = await getSupabaseClient();
      if (!supabase) return;
      // The recovery link signs the user in; a session means we can proceed.
      const { data } = await supabase.auth.getSession();
      if (data.session) setReady(true);
      const { data: listener } = supabase.auth.onAuthStateChange((event) => {
        if (event === "PASSWORD_RECOVERY" || event === "SIGNED_IN") setReady(true);
      });
      unsubscribe = () => listener.subscription.unsubscribe();
    })();
    return () => unsubscribe?.();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    const supabase = await getSupabaseClient();
    if (!supabase) {
      setLoading(false);
      return;
    }
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setLoading(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }
    notify("Password updated", "success");
    router.replace(APP_ENTRY);
  }

  return (
    <>
      <Head>
        <title>Choose a new password - KritiFin</title>
        <meta name="robots" content="noindex" />
      </Head>
      <AuthShell
        title="Choose a new password"
        subtitle="You followed a secure reset link — set your new password below."
      >
        {!isSupabaseConfigured ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5">
            <p className="text-sm leading-relaxed text-slate-600">
              Password reset needs sign-in to be configured. This environment
              runs in demo mode without accounts.
            </p>
          </div>
        ) : !ready ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5" role="status">
            <p className="text-sm leading-relaxed text-slate-600">
              Verifying your reset link… If this takes more than a few seconds,
              the link may have expired — request a new one.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5" noValidate data-testid="reset-form">
            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
                New password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="input"
                data-testid="reset-password"
              />
            </div>
            <div>
              <label htmlFor="confirm" className="mb-2 block text-sm font-medium text-slate-700">
                Confirm new password
              </label>
              <input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Repeat the password"
                className="input"
                data-testid="reset-confirm"
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
            <Button
              type="submit"
              loading={loading}
              disabled={!password || !confirm}
              size="lg"
              className="w-full"
              data-testid="reset-submit"
            >
              Update password
            </Button>
          </form>
        )}
      </AuthShell>
    </>
  );
}
