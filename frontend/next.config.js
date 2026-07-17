/** @type {import('next').NextConfig} */
const apiOrigin =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";
const apiHost = (() => {
  try {
    return new URL(apiOrigin);
  } catch {
    return new URL("http://localhost:8000");
  }
})();

const localApiConnect = [
  apiOrigin,
  `http://localhost:${apiHost.port || "8000"}`,
  `http://127.0.0.1:${apiHost.port || "8000"}`,
  // Default port when backend runs without overriding .env.local
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]
  .filter((v, i, a) => a.indexOf(v) === i)
  .join(" ");

// 'unsafe-eval' is required only by React Fast Refresh in development;
// production bundles run without it, so the deployed CSP is stricter.
const scriptSrc =
  process.env.NODE_ENV === "development"
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self' 'unsafe-inline'";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      scriptSrc,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      `connect-src 'self' ${localApiConnect} https:`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

// Sentry wraps the build only when configured; keeps local/dev builds clean.
let exported = nextConfig;
if (process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_AUTH_TOKEN) {
  const { withSentryConfig } = require("@sentry/nextjs");
  exported = withSentryConfig(nextConfig, {
    silent: true,
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT,
    // Source maps only upload in CI when SENTRY_AUTH_TOKEN is present.
    disableServerWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,
    disableClientWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,
  });
}

module.exports = exported;
