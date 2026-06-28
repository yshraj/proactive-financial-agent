import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* Global, page-agnostic tags only. Per-page SEO (title, description,
            canonical, Open Graph, Twitter) is set with next/head — see the
            landing page. */}
        <meta name="theme-color" content="#0284c7" />
        <link
          rel="icon"
          href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230284c7'/%3E%3Ctext x='16' y='22' font-family='Inter,system-ui,sans-serif' font-size='18' font-weight='700' fill='white' text-anchor='middle'%3EJ%3C/text%3E%3C/svg%3E"
        />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
