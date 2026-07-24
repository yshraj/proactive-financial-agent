#!/usr/bin/env node
// CI security gate: `npm audit` with an explicit allowlist.
//
// npm audit has no native ignore mechanism. next@14 (EOL) has published
// advisories whose only fix is the breaking next@16 upgrade — tracked as a
// separate piece of work. This wrapper fails on any HIGH or CRITICAL advisory
// that is not explicitly allowlisted below, so new vulnerabilities still
// block CI while the known-and-accepted ones don't.
//
// Run locally:  node scripts/check-audit.mjs   (from frontend/)

import { execSync } from "node:child_process";

// Accepted advisories. Every entry needs a reason; remove entries as soon as
// the underlying upgrade lands.
const ALLOWLIST = new Map([
  // ---- next@14.x — fixed only in next@16 (breaking major; planned upgrade).
  // The app uses the Pages Router without middleware, rewrites, image
  // remotePatterns, or RSC, which most of these advisories require.
  ["GHSA-9g9p-9gw9-jx7f", "next@16-only fix; Image Optimizer remotePatterns unused"],
  ["GHSA-h25m-26qc-wcjf", "next@16-only fix; RSC unused (Pages Router)"],
  ["GHSA-ggv3-7p47-pfv8", "next@16-only fix; rewrites unused"],
  ["GHSA-3x4c-7xq6-9pq8", "next@16-only fix; next/image disk cache — Vercel-managed"],
  ["GHSA-q4gf-8mx6-v5v3", "next@16-only fix; Server Components unused"],
  ["GHSA-8h8q-6873-q5fj", "next@16-only fix; Server Components unused"],
  ["GHSA-3g8h-86w9-wvmq", "next@16-only fix; middleware/proxy unused"],
  ["GHSA-ffhc-5mcf-pf4q", "next@16-only fix; App Router CSP nonces unused"],
  ["GHSA-vfv6-92ff-j949", "next@16-only fix; RSC cache unused"],
  ["GHSA-gx5p-jg67-6x7h", "next@16-only fix; beforeInteractive scripts unused"],
  ["GHSA-h64f-5h5j-jqjh", "next@16-only fix; Image Optimization API unused"],
  ["GHSA-c4j6-fc7j-m34r", "next@16-only fix; WebSocket upgrades unused"],
  ["GHSA-wfc6-r584-vfw7", "next@16-only fix; RSC responses unused"],
  ["GHSA-36qx-fr4f-26g5", "next@16-only fix; i18n routing unused"],
  ["GHSA-m99w-x7hq-7vfj", "next@16-only fix; Server Actions unused (Pages Router)"],
  ["GHSA-89xv-2m56-2m9x", "next@16-only fix; Server Actions + custom server unused"],
  ["GHSA-p9j2-gv94-2wf4", "next@16-only fix; rewrites unused"],
  // ---- postcss — build-time only, processes first-party CSS; npm's only
  // ---- in-range "fix" is a 4-major downgrade of @sentry/nextjs.
  ["GHSA-6g55-p6wh-862q", "build-time tool on first-party CSS; no sane in-range fix"],
]);

const BLOCKING = new Set(["high", "critical"]);

let report;
try {
  report = JSON.parse(execSync("npm audit --json", { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }));
} catch (err) {
  // npm audit exits non-zero when vulnerabilities exist; the JSON is still on stdout.
  if (!err.stdout) throw err;
  report = JSON.parse(err.stdout);
}

const advisories = new Map(); // GHSA id -> {severity, title, packages}
for (const [pkg, vuln] of Object.entries(report.vulnerabilities ?? {})) {
  for (const via of vuln.via ?? []) {
    if (typeof via !== "object" || !via.url) continue; // string = transitive pointer
    const id = via.url.split("/").pop();
    const existing = advisories.get(id) ?? { severity: via.severity, title: via.title, packages: new Set() };
    existing.packages.add(pkg);
    advisories.set(id, existing);
  }
}

const failures = [];
let accepted = 0;
for (const [id, adv] of advisories) {
  if (!BLOCKING.has(adv.severity)) continue;
  if (ALLOWLIST.has(id)) {
    accepted += 1;
    continue;
  }
  failures.push(`  ${id} [${adv.severity}] ${adv.title} (${[...adv.packages].join(", ")})`);
}

console.log(`npm audit: ${advisories.size} advisories; ${accepted} allowlisted high/critical.`);
if (failures.length > 0) {
  console.error(`FAIL — ${failures.length} high/critical advisories are not allowlisted:`);
  for (const line of failures) console.error(line);
  process.exit(1);
}
console.log("PASS — no unexpected high/critical advisories.");
