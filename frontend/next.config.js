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

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
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

module.exports = nextConfig;
