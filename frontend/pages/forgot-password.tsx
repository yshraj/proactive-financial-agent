import Head from "next/head";
import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "../components/AuthShell";
import { Button } from "../components/ui";
import { getSupabaseClient, isSupabaseConfigured } from "../lib/supabase/client";
import { ROUTES } from "../lib/routes";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const supabase = await getSupabaseClient();
    if (!supabase) {
      setLoading(false);
      return;
    }
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}${ROUTES.resetPassword}`,
    });
    setLoading(false);
    if (resetError) {
      setError(resetError.message);
      return;
    }
    setSent(true);
  }

  return (
    <>
      <Head>
        <title>Reset password - KritiFin</title>
        <meta name="robots" content="noindex" />
      </Head>
      <AuthShell
        title="Reset your password"
        subtitle="We'll email you a secure link to choose a new password."
        footer={
          <>
            Remembered it?{" "}
            <Link href={ROUTES.login} className="font-medium text-brand-600 hover:text-brand-700">
              Back to sign in
            </Link>
          </>
        }
      >
        {!isSupabaseConfigured ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-5">
            <p className="text-sm leading-relaxed text-slate-600">
              Password reset needs sign-in to be configured. This environment
              runs in demo mode without accounts.
            </p>
          </div>
        ) : sent ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 p-5" role="status">
            <p className="text-sm leading-relaxed text-emerald-800">
              If an account exists for <span className="font-medium">{email}</span>,
              a reset link is on its way. Check your inbox (and spam folder).
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5" noValidate data-testid="forgot-form">
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-700">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@firm.com"
                className="input"
                data-testid="forgot-email"
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
              disabled={!email}
              size="lg"
              className="w-full"
              data-testid="forgot-submit"
            >
              Email me a reset link
            </Button>
          </form>
        )}
      </AuthShell>
    </>
  );
}
