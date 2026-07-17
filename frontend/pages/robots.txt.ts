import type { GetServerSideProps } from "next";
import { SITE_URL } from "../lib/seo";

// Served at /robots.txt. Allows the marketing homepage; disallows the
// authenticated app and auth routes.
const DISALLOW = [
  "/dashboard",
  "/chat",
  "/brief",
  "/alerts",
  "/clients",
  "/admin",
  "/settings",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
];

function RobotsTxt() {
  return null;
}

export const getServerSideProps: GetServerSideProps = async ({ res }) => {
  const body = [
    "User-agent: *",
    ...DISALLOW.map((p) => `Disallow: ${p}`),
    "",
    `Sitemap: ${SITE_URL}/sitemap.xml`,
    "",
  ].join("\n");

  res.setHeader("Content-Type", "text/plain");
  res.setHeader("Cache-Control", "public, max-age=86400");
  res.write(body);
  res.end();
  return { props: {} };
};

export default RobotsTxt;
