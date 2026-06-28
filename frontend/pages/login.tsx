import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import { AuthShell } from "../components/AuthShell";
import { Button, ButtonLink, useToast } from "../components/ui";
import { getSupabaseClient, isSupabaseConfigured } from "../lib/supabase/client";
import { APP_ENTRY, ROUTES } from "../lib/routes";

/** Resolve a safe internal redirect target from the query string. */
function useRedirectTarget(): string {
  const router = useRouter();
  const raw = router.query.redirect;
  const value = Array.isArray(raw) ? raw[0] : raw;
  // Only allow internal paths to avoid open-redirects.
  return value && value.startsWith("/") ? value : APP_ENTRY;
}

export default function LoginPage() {
  const router = useRouter();
  const { notify } = useToast();
  const redirectTo = useRedirectTarget();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
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
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (signInError) {
      setError(signInError.message);
      setLoading(false);
      return;
    }
    notify("Signed in", "success");
    router.replace(redirectTo);
  }

  const signupHref = `${ROUTES.signup}?redirect=${encodeURIComponent(redirectTo)}`;

  return (
    <>
      <Head>
        <title>Sign in — Jarvis</title>
        <meta name="robots" content="noindex" />
      </Head>
      <AuthShell
        title="Welcome back"
        subtitle="Sign in to your Jarvis workspace."
        footer={
          isSupabaseConfigured ? (
            <>
              Don&apos;t have an account?{" "}
              <Link href={signupHref} className="font-medium text-brand-600 hover:text-brand-700">
                Sign up
              </Link>
            </>
          ) : undefined
        }
      >
        {isSupabaseConfigured ? (
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="email" className="overline mb-1.5 block">
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
              />
            </div>
            <div>
              <label htmlFor="password" className="overline mb-1.5 block">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="input"
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
              disabled={!email || !password}
              className="w-full"
            >
              Sign in
            </Button>
          </form>
        ) : (
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-5">
            <p className="text-sm text-gray-600">
              Sign-in isn&apos;t configured in this environment yet. You can
              continue straight into the app.
            </p>
            <ButtonLink href={redirectTo} className="mt-4 w-full">
              Continue to the app
            </ButtonLink>
          </div>
        )}
      </AuthShell>
    </>
  );
}
