#!/usr/bin/env node
/**
 * Sync shared env from project root .env into frontend/.env.local.
 * Run from repo root: node frontend/scripts/sync-env.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const rootEnvPath = path.join(root, ".env");
const outPath = path.join(root, "frontend/.env.local");

function parseEnv(text) {
  const out = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const i = trimmed.indexOf("=");
    const key = trimmed.slice(0, i).trim();
    const value = trimmed.slice(i + 1).trim();
    out[key] = value;
  }
  return out;
}

if (!fs.existsSync(rootEnvPath)) {
  console.error("Missing .env at project root. Copy .env.example first.");
  process.exit(1);
}

const env = parseEnv(fs.readFileSync(rootEnvPath, "utf8"));
const existing = fs.existsSync(outPath) ? parseEnv(fs.readFileSync(outPath, "utf8")) : {};

const merged = {
  NEXT_PUBLIC_API_URL:
    existing.NEXT_PUBLIC_API_URL || env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  NEXT_PUBLIC_SUPABASE_URL:
    existing.NEXT_PUBLIC_SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL || env.SUPABASE_URL || "",
  NEXT_PUBLIC_SUPABASE_ANON_KEY:
    existing.NEXT_PUBLIC_SUPABASE_ANON_KEY || env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
};

const lines = [
  "# Auto-synced for local dev — edit or re-run: node frontend/scripts/sync-env.mjs",
  `NEXT_PUBLIC_API_URL=${merged.NEXT_PUBLIC_API_URL}`,
];

if (merged.NEXT_PUBLIC_SUPABASE_URL) {
  lines.push(`NEXT_PUBLIC_SUPABASE_URL=${merged.NEXT_PUBLIC_SUPABASE_URL}`);
}
if (merged.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
  lines.push(`NEXT_PUBLIC_SUPABASE_ANON_KEY=${merged.NEXT_PUBLIC_SUPABASE_ANON_KEY}`);
}

lines.push("");
fs.writeFileSync(outPath, lines.join("\n"));

console.log(`Wrote ${outPath}`);
if (merged.NEXT_PUBLIC_SUPABASE_URL && !merged.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
  console.warn(
    "WARN: NEXT_PUBLIC_SUPABASE_ANON_KEY is missing. Add it to .env or frontend/.env.local"
  );
  console.warn("      Supabase Dashboard → Project Settings → API → anon public key");
}
