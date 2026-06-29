import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { AuthShell } from "../components/AuthShell";
import { Button, ButtonLink, useToast } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { getSupabaseClient, isSupabaseConfigured } from "../lib/supabase/client";
import { APP_ENTRY, ROUTES } from "../lib/routes";
import { safeRedirectPath } from "../lib/safeRedirect";

function useRedirectTarget(): string {
  const router = useRouter();
  return safeRedirectPath(router.query.redirect);
}

export default function SignupPage() {
  const router = useRouter();
  const { notify } = useToast();
  const { loading: authLoading, user } = useAuth();
  const redirectTo = useRedirectTarget();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [checkEmail, setCheckEmail] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured || authLoading || !user) return;
    router.replace(redirectTo);
  }, [authLoading, redirectTo, router, user]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const supabase = await getSupabaseClient();
    if (!supabase) {
      setLoading(false);
      return;
    }
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      // Where the email-confirmation link returns the user. Lands them straight
      // in the app (or the original deep link). Must be allow-listed in
      // Supabase → Authentication → URL Configuration → Redirect URLs.
      options: { emailRedirectTo: `${window.location.origin}${redirectTo}` },
    });
    if (signUpError) {
      setError(signUpError.message);
      setLoading(false);
      return;
    }
    // If email confirmation is required, there is no active session yet.
    if (data.session) {
      notify("Account created", "success");
      router.replace(redirectTo);
    } else {
      setCheckEmail(true);
      setLoading(false);
    }
  }

  const loginHref = `${ROUTES.login}?redirect=${encodeURIComponent(redirectTo)}`;

  return (
    <>
      <Head>
        <title>Create account - KritiFin</title>
        <meta name="robots" content="noindex" />
      </Head>
      <AuthShell
        title="Create your account"
        subtitle="Start turning client intelligence into prepared action."
        footer={
          isSupabaseConfigured ? (
            <>
              Already have an account?{" "}
              <Link href={loginHref} className="font-medium text-brand-600 hover:text-brand-700">
                Sign in
              </Link>
            </>
          ) : undefined
        }
      >
        {!isSupabaseConfigured ? (
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-5">
            <p className="text-sm text-gray-600">
              Sign-up isn&apos;t configured in this environment yet. You can
              continue straight into the app.
            </p>
            <ButtonLink href={redirectTo} className="mt-4 w-full" data-testid="continue-without-auth">
              Continue to the app
            </ButtonLink>
          </div>
        ) : checkEmail ? (
          <div role="status" className="rounded-xl border border-brand-100 bg-brand-50/50 p-5">
            <p className="text-sm text-brand-900">
              Check your inbox to confirm your email, then sign in to KritiFin.
            </p>
            <ButtonLink href={loginHref} variant="secondary" className="mt-4 w-full">
              Back to sign in
            </ButtonLink>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5" noValidate data-testid="signup-form">
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
                data-testid="signup-email"
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
                Password
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
                data-testid="signup-password"
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
              disabled={!email || password.length < 8}
              size="lg"
              data-testid="signup-submit"
              className="mt-2 w-full"
            >
              Create KritiFin account
            </Button>
          </form>
        )}
      </AuthShell>
    </>
  );
}
