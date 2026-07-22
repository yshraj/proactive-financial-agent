# KritiFin production-readiness audit — July 2026

_Principal engineer + QA + AI architect + security + release review. Companion
to the earlier RFC ([NEXT_PLAN.md](planning/NEXT_PLAN.md)); this document records the
audit findings, the changes made in this pass, and the forward roadmap._

---

## 1. Executive summary

KritiFin is an AI workspace for UK financial advisers (dashboard, RAG copilot,
meeting briefs, PDF/DOCX ingestion, Consumer Duty / vulnerability compliance
scanning, human review). Two engagements have taken it from an advanced demo to
a defensibly production-ready system:

1. **Trust foundation** (prior RFC, now committed in 15 logical commits):
   multi-tenancy with Postgres RLS, fail-closed auth, durable audit, durable
   jobs, document storage, observability, CI/CD.
2. **This audit**: closed the product-surface gaps that block real customers —
   branded error pages, SEO/share metadata, WCAG fixes verified by axe,
   surfaced silent error states, an AI-quality regression suite (which caught
   and fixed a real prompt-injection filter gap), failure-path Playwright
   coverage across desktop/mobile/tablet/cross-browser, and dead-code removal.

**State now:** 196 backend tests and 244 Playwright tests (chromium, firefox,
webkit, mobile, tablet) pass; frontend typecheck/lint/build clean; backend ruff
+ SQL/cache guard clean. The system is ready for a **controlled beta on
synthetic data**; the gate to real client PII is the operational cutover in
[pre-beta-checklist.md](pre-beta-checklist.md) (Supabase Pro/PITR, staging,
runtime-role cutover, drills), not further code.

**Headline recommendations:** (1) execute the pre-beta operational cutover;
(2) do **not** adopt LangChain/LangGraph/Graph RAG/MCP now — none clears the
value bar for this codebase yet (analysis below); (3) next real AI investment is
streaming + the online eval harness, then a scheduled-proactivity worker (the
one place an agentic loop earns its complexity).

---

## 2. Architecture review

**Stack:** Next.js 14 (pages router, TS, Tailwind, React Query) · FastAPI
(Python 3.9/3.12, psycopg2) · Postgres (Supabase, RLS) · Qdrant (vectors) ·
OpenAI (LLM + embeddings) · Supabase Auth + Storage · Render (API + worker) +
Vercel · Sentry.

**Shape:** clean service layer (`backend/app/services/*`) behind thin routers;
a request resolves JWT → `TenantContext` → tenant-bound DB cursor (GUCs) +
org-scoped cache/vectors. Ingestion is dual-path (LLM extract → Postgres;
chunk+embed → Qdrant) and now runs on a durable Postgres queue via a dedicated
worker. AI is a deterministic orchestration in `chat.py`/`monitor.py` over
centralised, versioned prompts.

**Strengths:** coherent layering with clear seams; four independent
tenant-isolation layers each with tests; parameterised SQL with a CI guard;
centralised prompts with a trust contract; strong existing UX component library
(loading/empty/error states, modal focus management).

**Weaknesses / debt (remaining, tracked in §17):** single in-memory cache per
instance (fine at one instance; Redis gated on scale-out); no streaming (AI
latency unmasked); Python 3.9 compatibility shims; Qdrant free-tier ceiling; no
malware scanning of uploads (validation only); brief/meeting persistence
deferred (the `meetings` table is designed but not yet built).

**Scalability risk:** the API is single-instance by design today. The blockers
to horizontal scale are all identified and gated (Redis for cache, already-done
Postgres queue for jobs). Nothing forces a rewrite.

---

## 3. Security report

Posture is strong for the stage. Covered: fail-closed auth (`AUTH_MODE`),
four-layer tenant isolation (RLS + scoped SQL + scoped cache + scoped vectors),
parameterised SQL (+ CI guard), per-org rate limiting, upload validation
(magic bytes + zip-bomb guards + extraction caps), prompt-injection posture
(delimited untrusted content, tightened filter, no tool-calls on untrusted
data), PII-scrubbed logs/Sentry, tightened CORS/CSP, secret scanning + rotation
runbook, append-only audit. Full analysis: [security-threat-model.md](security-threat-model.md).

**This pass** tightened the injection filter (a real gap the new eval set
caught) and hardened the production CSP (no `unsafe-eval`).

**Accepted residual risks:** no malware scanning (Phase 2); OpenAI US
processing (disclosed; Azure UK South is the Phase 3 option); demo mode present
in code (triple-guarded); anon key reachability (inert under RLS + revoked
grants). CSRF is N/A (pure Bearer auth) and must be revisited only if cookie
auth is ever introduced.

---

## 4. QA report

Manual audit of every page (navigation, error/empty/loading states, forms,
validation, uploads, auth, responsive). Findings and fixes:

- **Fixed:** missing 404/500 pages; silent failures on settings audit,
  dashboard "recently completed", and chat client scoping (now show an error
  with retry rather than a misleading empty state); upload error copy for
  413/400 alongside the existing 409 duplicate handling.
- **Already solid:** React Query retry + `ErrorState`/`EmptyState`/`Skeleton`
  usage across the core pages; client-side upload validation (extension, size,
  MIME, magic bytes) before any network call; modal focus management.
- **No console errors** in the app; no `console.log`, TODO, or FIXME left in
  `pages`/`components`/`lib`/`hooks`.

---

## 5. Playwright report

244 passing across **chromium, firefox, webkit, mobile-chromium (Pixel 5), and
tablet-chromium (iPad gen 7)**; page-object model with reusable fixtures and a
console-error gate. Added this pass:

- `resilience.spec.ts` — 404, injected API 500/401/network-loss with retry
  recovery, invalid/unsupported/duplicate upload rejection, tablet layout.
- `accessibility.spec.ts` — axe WCAG scans + keyboard/skip-link + mobile-drawer
  focus.
- De-flaked the AI Copilot/Brief journeys (wait on the response, not just DOM);
  cross-browser console-noise filtering so deliberate-failure tests stay green.

**Coverage of requested journeys:** homepage, login/logout, dashboard, client
list/detail, meeting briefs, document upload + processing, AI Copilot,
compliance scan, approval workflow, filtering, unauthorized access, 404,
API-500, upload validation, mobile/tablet/desktop, cross-browser — all present.
Session-timeout is exercised as a 401-mid-session error state; a true expiry
redirect is a P2 backlog item (needs the auth-mode E2E environment).

---

## 6. Accessibility report

Automated axe (WCAG 2.0/2.1 A/AA) scans gate serious+critical on landing,
login, dashboard, clients, ingestion, settings, and 404. Fixes this pass:
mobile-drawer focus trap + restore; error toasts as assertive live regions;
labels on transcript + compliance-scan fields; valid `<dl>` structure on the
posture card; contrast lifts on secondary text (slate-400 → slate-500). Strong
pre-existing base: `lang`, landmarks, skip link, `aria-current`, modal focus,
semantic headings. Remaining (moderate, tracked): a full manual screen-reader
pass and a contrast audit of brand-colored controls.

---

## 7. SEO report

Public surface is the landing page (app + auth pages correctly `noindex`).
Fixed: `og:image`/`twitter:image` (generated on-brand card), `og:locale`,
`SoftwareApplication` JSON-LD, PWA manifest + apple-touch/favicon PNGs, and
`robots.txt` coverage of `/clients` and the auth routes. Title/description/
canonical/OG/Twitter were already present. `sitemap.xml` correctly lists only
`/`. Remaining (low): a dedicated marketing OG per-section and richer
structured data if a public pricing/blog surface is added.

---

## 8. Performance report

Already good: `next/font` self-hosting, lazy-loaded modals/markdown/digest,
React Query dedupe with sane `staleTime`, memoized cards, backend connection
pooling + TTL caches, parallel embed+DB on cache miss. Recommendations (backlog,
not done — they need production signal to prioritise): SSE streaming to mask AI
latency (biggest perceived win); list virtualization + server pagination at
book scale; trim framer-motion from the landing/auth bundle if LCP needs it;
Qdrant payload-index monitoring. No performance regressions introduced.

---

## 9. AI architecture review

Pipeline: dual-path ingestion → chunk (char-based, 2000/200) → OpenAI
embeddings (1536, cosine) → org+client-filtered Qdrant retrieval with a score
floor → hybrid context assembly (trusted structured records + untrusted
document excerpts) → centralised versioned prompts → completion with mandatory
citations and a no-invention/no-regulated-advice contract. Human review is a
post-hoc register + audit event.

**Assessment:** the design is sound and appropriately deterministic for a
regulated domain — retrieval and orchestration are plain, debuggable Python
with tenant isolation enforced below the AI layer. The correct near-term
investments are **quality and latency**, not framework adoption: streaming,
the online eval harness (§14, doc added), and citation post-validation.

---

## 10. LangChain evaluation

**Recommendation: do not adopt.** Pros: prebuilt loaders/splitters/retrievers,
faster prototyping. Cons for this codebase: the pipeline is ~200 lines of clear
Python with tenant isolation threaded through `get_cursor`/`search_qdrant`;
LangChain would add a heavy dependency, abstraction layers that obscure exactly
the tenant-scoping we must audit, version churn, and non-trivial migration
effort — for near-zero functional gain. Vendor lock-in: moderate. DX:
familiar but a net negative here given the isolation-critical seams. Revisit
only if we need many pluggable retrievers/loaders we don't want to maintain.

---

## 11. LangGraph evaluation

**Recommendation: not now; reconsider for one specific future feature.** The
current request/response AI flows are deterministic and do not need a graph
runtime — a state machine over these would be complexity for its own sake. The
**one** place LangGraph (or a small hand-rolled state machine) could earn its
keep is **scheduled proactivity** (a nightly agent that reviews the book,
drafts outreach, and queues human-approved actions) — a genuinely multi-step,
resumable, human-in-the-loop workflow. Even there, start with a deterministic
worker + the existing job queue; adopt LangGraph only if branching/retry state
becomes hard to manage by hand.

---

## 12. Graph RAG evaluation

**Recommendation: do not adopt now; strong candidate later.** The document set
(fact-finds, suitability reports, annual reviews, meeting notes, emails) is
genuinely relational — the same household, products, and commitments recur
across documents and time — so entity linking, timeline reconstruction, and
cross-document "what did we advise and did we follow through" reasoning are
real future wins. But: current scale (single adviser books, tens of docs per
client) is served well by vector + structured hybrid retrieval; a graph adds a
second datastore (Neo4j/Memgraph or `pgrouting`/AGE in Postgres), an
entity-extraction + resolution pipeline, sync/consistency burden, and latency.
**Justified trigger:** when customers ask cross-document/temporal questions the
current RAG answers poorly, or at multi-adviser-firm scale. **If adopted:**
nodes = Client/Person/Product/Policy/Meeting/Document/Commitment/Adviser; edges
= holds/attended/recommended/superseded/follows-up; extract during ingestion
with the LLM, resolve entities per-org (never across the tenant boundary),
prefer Postgres AGE first to avoid a new datastore, and use graph retrieval to
*expand* vector hits rather than replace them.

---

## 13. MCP evaluation

**Recommendation: not for the product runtime; useful for internal tooling.**
Model Context Protocol shines for connecting external assistants (e.g. Claude
Desktop, IDE agents) to tools. KritiFin's server already owns its Supabase,
Qdrant, and storage access with tenant isolation enforced in-process — wrapping
those as MCP tools for the product's own LLM calls would add a protocol hop and
an isolation surface for no user-facing gain. Where MCP *does* add value:
**internal/ops** — a read-only MCP server exposing (RLS-respecting) Supabase
queries, Qdrant search, and log/metrics lookups to the team's own AI tooling,
and eventual customer-facing integrations (Outlook/Google calendar, CRM) where
MCP's standard tool interface reduces bespoke glue. Treat as a Phase 3 internal
productivity tool, not core architecture.

---

## 14. Database review

Schema (Alembic 0001–0006): `organizations`/`users`/`org_memberships` tenancy;
`org_id` on `clients`/`alerts`/`ingested_documents` with FKs and composite
indexes; durable `audit_log` (append-only), `ai_outputs`, `jobs`,
`conversations`/`conversation_messages`; a designed-but-unbuilt `meetings`
table. RLS on every table via the non-owner `kritifin_app` role with GUC-keyed
policies + bootstrap policies for provisioning. Migration order is
expand-and-backfill; every revision has a tested downgrade; CI runs
up/down/base drills. **Recommendations (backlog):** build the `meetings` table
when brief persistence lands; add `audit_log` monthly partitioning + BRIN on
`created_at` at scale; add a covering index for the hot pulse query if k6 shows
need; introduce `roles`/invitations for multi-adviser firms (Phase 3).

---

## 15. Observability plan

In place: Sentry (both apps, PII-scrubbed, release-tagged), JSON logs with
request/org/user correlation, access logging, global exception handler,
`/health` + deep `/health/ready` (DB, Qdrant, auth posture, migration version),
per-request LLM usage/cost telemetry. Planned: uptime monitors on
`/health/ready` + homepage (setup step, not code), a weekly ops review
(errors, job failures, LLM spend), and — only if Sentry tracing proves
insufficient — OpenTelemetry (FastAPI + psycopg + httpx) with OTLP export. Full
plan in the RFC §7; no gap blocks beta.

---

## 16. CI/CD plan

`ci.yml`: ruff + SQL/cache guard + pytest against a real Postgres (3.9 and
3.12, coverage floor); migration up/down/base reversibility; frontend
lint/typecheck/build; Playwright (chromium + tablet + firefox vs mock API);
gitleaks + pip-audit + npm audit. Deploy: Render blueprint with pre-deploy
`alembic upgrade head`, health-gated zero-downtime rollout, "wait for CI".
Nightly authenticated staging E2E + Dependabot. This pass added firefox +
tablet to the PR E2E job.

---

## 17. Technical debt list (ranked by ROI)

1. No streaming — AI latency fully unmasked (high perceived-quality ROI).
2. Brief/meeting persistence not built (`meetings` table designed only).
3. Single in-memory cache — Redis gated on horizontal scale.
4. No malware scanning of uploads (validation only).
5. Python 3.9 compat shims — pin 3.12 and drop `from __future__` gradually.
6. framer-motion weight on landing/auth bundle.
7. mypy not yet adopted (services first).
8. Coverage floor at 65% — ratchet toward 80% as fake-backed AI/storage paths land.
9. Full manual screen-reader + brand-control contrast pass outstanding.

## 18. Risk register (top items)

- Cross-tenant exposure — Critical/Low-now — four-layer isolation + CI proofs — Eng — P0(mitigated).
- Operational cutover incomplete (no PITR/staging yet) — High/Medium — pre-beta checklist — Founder+Eng — P0.
- AI latency hurts adoption — Medium/High — streaming + caching — Eng — P1.
- LLM cost/outage — Medium/Medium — telemetry, tiering, budget alarm, fallbacks — Eng — P1.
- Upload malware — Medium/Low — validation now, scanning Phase 2 — Eng — P1.
- Solo bus factor — Medium/Medium — runbooks, ADRs, boring stack — Founder — P1.
- UK residency (OpenAI US) — Medium/Low — disclosed; Azure UK South option — Founder — P2.

## 19. Production-readiness checklist (code vs ops)

**Code (done):** no TS errors; no lint errors; frontend build clean; 244
Playwright pass; 196 backend tests pass; no broken routes; no console errors;
axe serious+critical clean on scanned pages; SEO metadata present; no dead code
introduced. **Ops (outstanding — [pre-beta-checklist.md](pre-beta-checklist.md)):**
Supabase Pro + PITR, staging environment, runtime-role cutover, uptime
monitors, rollback + restore + worker-kill drills.

## 20. Prioritized engineering backlog

Maintained in [pre-beta-checklist.md](pre-beta-checklist.md) (ops gate) and the
RFC backlog (~85 tasks). New items from this audit: build `meetings` table +
brief persistence; SSE streaming; online AI eval harness + golden dataset;
session-expiry redirect + E2E; manual a11y/screen-reader pass; framer-motion
bundle trim; roles/invitations; Graph RAG spike (gated on the trigger in §12).

## 21. Commits created

This audit (working tree clean after each): `feat(errors)` 404/500 ·
`fix(seo)` share image/JSON-LD/robots · `fix(accessibility)` focus/labels/
contrast/live-regions/dl · `refactor` dead-code · `test(ai)` quality suite +
injection filter · `test(playwright)` resilience/a11y/tablet/de-flake · plus the
CI update folding firefox+tablet into PR E2E. These follow the 15 commits that
captured the prior trust-foundation RFC (`feat(db)`, `feat(auth)`,
`feat(multitenancy)`, `feat(audit)`, `feat(jobs)`, `feat(storage)`,
`feat(observability)`, `feat(api)`, `ci`, `docs`, etc.).

## 22. Remaining risks

All P0 *code* risks are mitigated and tested. The material remaining risk is
**operational**: real PII must not be enabled until the pre-beta checklist is
signed (backups/PITR, staging, runtime-role cutover, rehearsed drills). Product
risks (AI latency, cost, adoption) are understood and backlogged, not blocking.

## 23. Recommendations for the next milestone

1. Execute the pre-beta operational cutover and open a synthetic-data beta.
2. Ship SSE streaming + the online eval harness (biggest AI-quality/perceived
   -latency wins) before expanding the beta.
3. Build `meetings`/brief persistence — completes the "meeting" domain the UI
   already implies.
4. Hold the line on frameworks: no LangChain/LangGraph/Graph RAG/MCP until the
   documented triggers fire. Re-evaluate Graph RAG when customers ask
   cross-document/temporal questions the current RAG answers poorly.
