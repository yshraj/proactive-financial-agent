import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* Global, page-agnostic tags only. Per-page SEO (title, description,
            canonical, Open Graph, Twitter) is set with next/head — see the
            landing page. */}
        <meta name="theme-color" content="#3B6FFF" />
        <link
          rel="icon"
          href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='12' fill='%230F172A'/%3E%3Cpath d='M13 9v22' stroke='white' stroke-width='3.6' stroke-linecap='round'/%3E%3Cpath d='M28 10 15 20l13 10' stroke='white' stroke-width='3.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3Ccircle cx='27.5' cy='10.5' r='2.4' fill='%2393C5FD'/%3E%3C/svg%3E"
        />
        <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <link rel="manifest" href="/site.webmanifest" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
