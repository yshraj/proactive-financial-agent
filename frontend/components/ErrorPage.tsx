import Head from "next/head";
import Link from "next/link";
import { BrandLogo } from "./BrandLogo";
import { Button, ButtonLink } from "./ui";
import { APP_ENTRY, ROUTES } from "../lib/routes";

/**
 * Shared full-page error layout for the custom 404/500 pages. Renders bare
 * (no app shell) so it works signed-in or signed-out, and offers safe exits
 * instead of Next's default unstyled screens.
 */
export function ErrorPage({
  code,
  title,
  description,
  showRetry = false,
}: {
  code: string;
  title: string;
  description: string;
  showRetry?: boolean;
}) {
  return (
    <>
      <Head>
        <title>{`${title} - KritiFin`}</title>
        <meta name="robots" content="noindex" />
      </Head>
      <main className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-6 py-16">
        <Link href={ROUTES.home} aria-label="KritiFin home">
          <BrandLogo />
        </Link>
        <p className="mt-10 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
          Error {code}
        </p>
        <h1 className="mt-3 text-center text-3xl font-semibold tracking-tight text-slate-950">
          {title}
        </h1>
        <p className="mt-3 max-w-md text-center text-sm leading-relaxed text-slate-600">
          {description}
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <ButtonLink href={APP_ENTRY} data-testid="error-page-home">
            Go to dashboard
          </ButtonLink>
          {showRetry ? (
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Try again
            </Button>
          ) : (
            <ButtonLink href={ROUTES.home} variant="secondary">
              Back to homepage
            </ButtonLink>
          )}
        </div>
      </main>
    </>
  );
}
