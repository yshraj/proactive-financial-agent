import type { GetServerSideProps } from "next";
import { SITE_URL } from "../lib/seo";

// Served at /sitemap.xml. Only public (indexable) pages are listed — the app
// and auth routes are disallowed in robots.txt.
const PUBLIC_PATHS = ["/"];

function SiteMap() {
  return null;
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const lastmod = new Date().toISOString().slice(0, 10);
  const urls = PUBLIC_PATHS.map(
    (p) =>
      `  <url>\n    <loc>${SITE_URL}${p}</loc>\n    <lastmod>${lastmod}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n  </url>`
  ).join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;

  res.setHeader("Content-Type", "application/xml");
  res.setHeader("Cache-Control", "public, max-age=86400");
  res.write(xml);
  res.end();
  return { props: {} };
};

export default SiteMap;
