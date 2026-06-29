# Implementation Plan — Proactive Financial Agent (Jarvis)

> Source of truth for findings: [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md). See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for the changelog.
> Working assumption: **1 full-time engineer** (adjust calendar time accordingly if more). Estimates are engineering effort, not calendar duration.

---

## Progress (updated 28 Jun 2026 — RC hardening pass)

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M0 — Emergency Lockdown** | ✅ Done | API-key gate, guarded `clear-data`, upload cap, rate limits, Next.js patched. See `RELEASE_NOTES.md`. |
| **M2 — Architecture (frontend)** | ✅ Done | Shared API client, types, hooks (React Query), error boundary/toast, singleton backend clients, structured logging. |
| **M2 — Architecture (infra)** | ⛔ Deferred | Redis cache + async ingestion queue need a live Redis/DB. |
| **M3 — UI/UX Overhaul** | ✅ Mostly | Responsive shell, component library, states, a11y, settings hub, tokens done. Onboarding wizard (M3-T09) + landing/pricing (M3-T14) remain. |
| **M1 — Auth/Tenancy/RLS** | ⛔ Next | Blocked on auth provider + live DB; the M0 key gate is interim only. |
| **M4–M7** | ⛔ Deferred | Billing, audit/DSAR, streaming/memory, integrations — external services. |
| **M8 — QA harness** | ✅ Partial | Playwright e2e (34 tests, desktop+mobile) + backend security test in place; CI wiring + RTL unit tests remain. |

See `RELEASE_NOTES.md` for the full changelog and environment notes.

---

## How to use this document

- Each task has a **stable ID** (e.g. `M1-T03`) so it can be referenced in later agent runs and PRs.
- **One milestone ≈ one focused agent run / PR series.** Do not start a milestone until its **dependencies** are green.
- Treat every `[ ]` as a reviewable checklist item. Check them off as PRs merge.
- **"Launch gate"** = the set of P0 items that must ship before charging a single customer (see [§ Launch Gate](#launch-gate-definition-of-done-for-paid-launch)).

### Prioritization framework

| Priority | Meaning | Rule of thumb |
|----------|---------|---------------|
| **P0** | Launch-blocking / critical | Cannot have paying customers (or safe operation) without it. |
| **P1** | High | Needed for a *credible* paid launch & early retention. |
| **P2** | Medium | Improves conversion/retention/efficiency; can trail launch. |
| **P3** | Future | Differentiation / enterprise / scale. |

### Effort scale

| Size | Eng effort | |
|------|-----------|--|
| **XS** | < 0.5 day | trivial |
| **S** | ~1 day | small |
| **M** | 2–3 days | medium |
| **L** | ~1 week | large |
| **XL** | 2+ weeks | epic (should usually be split) |

---

## Milestone overview

| # | Milestone | Theme | Maps to prompt-run | Priority weight | Effort | Gate? |
|---|-----------|-------|--------------------|-----------------|--------|-------|
| **M0** | Emergency Lockdown | Stop the bleeding (security hotfix) | (do now) | P0 | ~S | ✅ pre-req |
| **M1** | Identity, Tenancy & RLS | Accounts + multi-tenant foundation | part of Prompt 5 (foundation first) | P0 | ~XL | ✅ |
| **M2** | Architecture Refactor & Platform Hardening | Clean codebase, API layer, Redis, async jobs, observability | **Prompt 4** | P0/P1 | ~XL | ✅ (partial) |
| **M3** | UI/UX Overhaul | Responsive, design system, onboarding, states | **Prompt 3** | P1 | ~XL | ✅ (responsive only) |
| **M4** | Commercialization | Billing, plans, entitlements, rate limits, usage | **Prompt 5** | P0/P1 | ~L | ✅ (billing+limits) |
| **M5** | SaaS Features | Teams/roles, settings hub, notifications, email, audit, analytics, flags | **Prompt 5** | P1/P2 | ~XL | partial |
| **M6** | AI Experience | Prompting, memory, context, streaming, long-running jobs, approvals | **Prompt 6** | P1/P2 | ~L | — |
| **M7** | Close-the-Loop & Integrations | Send/log actions, tasks, calendar, CRM, scheduled digests | (extends Prompt 5/6) | P1/P2 | ~XL | — |
| **M8** | Production Readiness & Polish | Bugs, a11y, tests, perf, SEO, deploy, final polish | **Prompts 7 & 8** | P0/P1 | ~L | ✅ |

> **Sequencing note (important):** The prompt workflow lists UI (Prompt 3) before Architecture (Prompt 4). I recommend a small adjustment: do **M0 → M1 → the responsive shell + design tokens from M3 (M3-T01..T03)** first, then **M2 architecture**, then the **rest of M3**. Rationale: rebuilding the UI *before* auth/tenancy exists means rebuilding it again once routes, sessions, and account chrome land. Foundations first prevents rework. The dependency graph below encodes this.

---

## M0 — Emergency Lockdown  ·  Priority P0  ·  Effort ~S  ·  Deps: none

> From `PROJECT_REVIEW.md` §5, §10, §14.1. Goal: make the currently-deployed demo not a liability **today**. This is a stopgap before M1, not the real auth.

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M0-T01 | Put a shared secret / API key (or HTTP basic auth) in front of **every** API route via FastAPI dependency | P0 | S | — |
| M0-T02 | Disable or hard-guard `POST /api/settings/clear-data` (remove from prod, or require secret + explicit confirm token) | P0 | XS | M0-T01 |
| M0-T03 | Add a request body/file **size limit** + reject oversized uploads before `await file.read()` | P0 | XS | — |
| M0-T04 | Add a basic per-IP rate limit (e.g. `slowapi`) on LLM endpoints to cap cost-abuse | P0 | S | — |
| M0-T05 | `npm audit fix` + bump `next` off the flagged advisory version | P0 | XS | — |
| M0-T06 | Rotate any keys that may have been exposed during the public demo | P0 | XS | — |

**Checklist**
- [ ] No endpoint is reachable without the shared secret (verified with curl)
- [ ] `clear-data` cannot be triggered anonymously
- [ ] Oversized upload returns 413 without reading the whole file into memory
- [ ] LLM endpoints rate-limited; verified by hammering locally
- [ ] `npm audit` shows 0 critical/high; Next.js upgraded
- [ ] Demo keys rotated and old ones revoked

---

## M1 — Identity, Tenancy & RLS  ·  Priority P0  ·  Effort ~XL  ·  Deps: M0

> From `PROJECT_REVIEW.md` §5, §7(1–3), §10(1–3,8). **The single most important milestone.** Everything downstream assumes a tenant context. Recommended stack: **Supabase Auth + Postgres RLS** (fits existing Postgres) *or* Clerk Organizations.

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M1-T01 | Choose & document auth/tenancy approach (Supabase Auth+RLS vs Clerk) in an ADR | P0 | S | — |
| M1-T02 | Schema: add `users`, `firms`/`workspaces`, `workspace_members(role)`, `subscriptions` tables + migration | P0 | M | M1-T01 |
| M1-T03 | Add `workspace_id` to every domain table (`clients`, `alerts`, `ingested_documents`) + backfill/migration + indexes | P0 | M | M1-T02 |
| M1-T04 | Enable **Postgres RLS** policies on all tenant tables; service-role for webhooks only | P0 | L | M1-T03 |
| M1-T05 | Backend auth dependency: resolve `user`→`workspace`→`role` on every request; inject `workspace_id` into all queries | P0 | L | M1-T02 |
| M1-T06 | Scope **Qdrant** payload filter by `workspace_id` on all upserts & searches | P0 | M | M1-T03 |
| M1-T07 | Scope **all cache keys** by `workspace_id` (prevents cross-tenant leakage) | P0 | S | M1-T05 |
| M1-T08 | Frontend: signup / login / logout / password reset / email verify pages | P0 | L | M1-T01 |
| M1-T09 | Frontend: protected routes + session handling + auth header on API client | P0 | M | M1-T08, M2-T03 |
| M1-T10 | Roles & permissions model (owner / adviser / paraplanner / admin) + server+client gating helpers | P1 | M | M1-T05 |
| M1-T11 | Team invitations (invite, accept, revoke) | P1 | M | M1-T10 |
| M1-T12 | Tests: RLS isolation tests (tenant A cannot read tenant B), auth guard tests | P0 | M | M1-T04, M1-T05 |

**Checklist**
- [ ] ADR committed; stack chosen
- [ ] All domain tables carry `workspace_id`, indexed
- [ ] RLS proven: automated test shows tenant A ↔ B fully isolated (DB, Qdrant, cache)
- [ ] Every API route requires a valid session and scopes to the caller's workspace
- [ ] Signup→login→logout→reset flows work; routes are protected
- [ ] Roles enforced server-side (not just hidden in UI)
- [ ] Invitations work end-to-end

---

## M2 — Architecture Refactor & Platform Hardening  ·  Priority P0/P1  ·  Effort ~XL  ·  Deps: M1 (lands alongside)

> From `PROJECT_REVIEW.md` §8, §9. **This is "Prompt 4" (no new features).** Some items (Redis, async ingestion) are P0 because the current in-proc cache + sync ingestion break under real load/multi-worker.

### Backend
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M2-T01 | App-level DB connection **pool** (replace per-request `psycopg2.connect`); remove unused `sqlalchemy` or adopt it intentionally | P1 | S | — |
| M2-T02 | Replace in-memory cache with **Redis** (tenant-scoped keys, TTLs preserved) | P0 | M | M1-T07 |
| M2-T05 | Move ingestion **off the request path** → job queue (RQ/Arq/Celery) + status records | P0 | L | M2-T02 |
| M2-T06 | Singleton/module-level clients for OpenAI & Qdrant (stop re-instantiating per call) | P1 | S | — |
| M2-T07 | Service/repository layer: extract SQL + LLM orchestration out of routers | P1 | L | — |
| M2-T08 | Replace broad `except Exception` with typed handling; stop returning raw error strings to clients | P1 | M | M2-T07 |
| M2-T09 | Structured logging (JSON, levels, request IDs) + correlation across ingestion/chat/monitor | P1 | M | — |
| M2-T10 | **Sentry** (or equivalent) error reporting, backend + frontend | P0 | S | — |
| M2-T11 | Pagination + sane limits on all list endpoints (`/alerts`, `/clients`, pulse review-overdue) | P1 | M | M2-T07 |
| M2-T12 | Replace fragile string contracts (synthetic IDs, `---TALKING_POINTS---`, regex JSON) with structured fields / function-calling | P2 | M | M2-T07 |

### Frontend
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M2-T03 | Shared typed **API client** (`lib/api.ts`) + single `API_BASE` + auth header injection | P0 | S | — |
| M2-T04 | Shared **types** (`types.ts`) generated from / matched to backend models (kill duplicated `AlertRow`, helpers) | P1 | S | M2-T03 |
| M2-T13 | Adopt **React Query (TanStack)** for fetching/caching/dedup/retry; remove hand-rolled loading/error state | P1 | M | M2-T03 |
| M2-T14 | Reusable hooks (`usePulse`, `useAlerts`, `useChat`, `useBrief`) + shared formatters/label maps | P1 | M | M2-T13 |
| M2-T15 | Global error boundary + toast system | P1 | S | M2-T03 |
| M2-T16 | Repo hygiene: remove dead refs (non-existent seed script), add `.nvmrc`/engines | P2 | XS | — |

**Checklist**
- [ ] No per-request DB/Qdrant/OpenAI client instantiation
- [ ] Redis-backed cache; survives restart; tenant-scoped
- [ ] Ingestion is async; upload returns a job id; status is polled/streamed (real, not faked)
- [ ] Routers are thin; logic lives in services with unit tests
- [ ] Sentry capturing errors; structured logs with request IDs
- [ ] One API client + one types module; no duplicated constants/types
- [ ] React Query in place; navigations don't blindly refetch
- [ ] All list endpoints paginated

---

## M3 — UI/UX Overhaul  ·  Priority P1  ·  Effort ~XL  ·  Deps: M2-T03/T04/T13 (API+types+query), M1 (for account chrome)

> From `PROJECT_REVIEW.md` §3, §4. **This is "Prompt 3."** Split into an *early* responsive/token slice (do before M2) and the *full* overhaul (after M2 foundations).

### Early slice (do before/with M2)
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M3-T01 | Responsive app shell: collapse sidebar to top-bar + drawer below `md:` (fixes broken mobile across all pages) | P0 | M | — |
| M3-T02 | Design tokens: brand color, spacing, radius as CSS vars / Tailwind theme (replace hard-coded `sky-600`) | P1 | S | — |
| M3-T03 | Icon system (e.g. Lucide) replacing emoji; favicon + brand + title template + OG meta | P2 | S | M3-T02 |

### Full overhaul
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M3-T04 | Component library pass: `Button`, `Tooltip`, `Card`, `Badge`, `Table`, `Modal`, `Input`, `Select` with all microstates (default/hover/focus/active/disabled/loading) | P1 | L | M3-T02 |
| M3-T05 | Dashboard redesign: 2-column hierarchy, dedupe Pulse-vs-table, make KPIs actionable filter entry-points | P1 | M | M3-T04 |
| M3-T06 | Designed **empty states** as onboarding (one CTA, sample-data load, teaching copy) on every list/page | P1 | M | M3-T04 |
| M3-T07 | **Loading skeletons** that match content layout (replace generic spinners/fake progress) | P1 | M | M3-T04 |
| M3-T08 | Human-voiced, recoverable **error states** (replace "Failed: 500") | P1 | S | M2-T15 |
| M3-T09 | First-run **onboarding flow** (connect/upload → first alerts → first question) + one-click sample dataset | P1 | M | M3-T06, M1 |
| M3-T10 | Account chrome: user avatar/menu, workspace switcher, breadcrumbs in header | P1 | M | M1-T09 |
| M3-T11 | Settings **hub** scaffolding (profile, firm, notifications, integrations, data/privacy, billing tabs) | P1 | M | M1-T09 |
| M3-T12 | Fix cross-page inconsistencies (shared label map: `FOLLOW_UP`→"Waiting on client", etc.); consistent button casing | P1 | S | M2-T14 |
| M3-T13 | Accessibility pass: focus trap in modals, `role=dialog`/`aria-modal`, `aria-live` answer region, skip link, contrast, keyboard nav → target WCAG AA | P1 | M | M3-T04 |
| M3-T14 | Marketing **landing page** + **pricing page** | P1 | M | M3-T02 |

**Checklist**
- [ ] Fully usable on 390px mobile (every page) — verified with Playwright
- [ ] One component library; every interactive element has 6 microstates
- [ ] Empty/loading/error states designed (not stubbed) everywhere
- [ ] First-run onboarding + sample data works
- [ ] Account/workspace chrome present; settings hub navigable
- [ ] No raw enum strings in UI; labels consistent across pages
- [ ] WCAG AA checks pass (axe clean on key pages)
- [ ] Landing + pricing pages live

---

## M4 — Commercialization  ·  Priority P0/P1  ·  Effort ~L  ·  Deps: M1, M2-T02 (Redis)

> From `PROJECT_REVIEW.md` §7(4–6), §11 (Critical). **Part of "Prompt 5."** Stripe attached to the **workspace**; webhooks as source of truth; **app-layer** quota enforcement (Stripe meters are billing, not enforcement).

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M4-T01 | Define plans/tiers (Free/Pro/Team) + feature matrix + limits | P0 | S | — |
| M4-T02 | Stripe: products/prices, Checkout, Customer Portal | P0 | M | M4-T01 |
| M4-T03 | Idempotent Stripe **webhook** handlers → persist subscription state to `subscriptions` | P0 | M | M4-T02, M1-T02 |
| M4-T04 | **Entitlements layer** (DB defines plans/features; Stripe = payment status truth; cached in Redis) | P0 | M | M4-T03, M2-T02 |
| M4-T05 | Server + client **feature gating** via entitlements (never trust client) | P0 | M | M4-T04 |
| M4-T06 | **Usage metering** (track in our DB first) for LLM calls / docs / seats | P0 | M | M2-T02 |
| M4-T07 | **Quota / rate-limit enforcement** per workspace (replaces M0 stopgap) | P0 | M | M4-T06 |
| M4-T08 | Billing UI in settings hub (current plan, usage, upgrade, invoices) | P1 | M | M3-T11, M4-T04 |

**Checklist**
- [ ] Checkout → webhook → entitlement unlock works end-to-end (test mode)
- [ ] Downgrade/cancel/past-due states correctly gate features
- [ ] Per-workspace usage tracked locally and enforced before hitting paid APIs
- [ ] Billing self-serve in-app (plan, usage, invoices, portal)

---

## M5 — SaaS Features  ·  Priority P1/P2  ·  Effort ~XL  ·  Deps: M1, M2, M3-T11, M4

> From `PROJECT_REVIEW.md` §11 (Critical/High), §12. **Remainder of "Prompt 5."**

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M5-T01 | **Audit log** (immutable; who did what, when) — compliance baseline | P0 | M | M1, M2-T09 |
| M5-T02 | UK **data residency** posture (region pinning) + documented data flows | P0 | M | M1 |
| M5-T03 | **DSAR / right-to-erasure** workflow + account/data deletion self-serve | P0 | M | M5-T01 |
| M5-T04 | Transactional **email** provider + templates (verify, invite, reset, receipts) | P1 | S | M1-T08 |
| M5-T05 | **Notification center** (in-app + email; later Slack/Teams) | P1 | M | M5-T04 |
| M5-T06 | Full **settings hub** content (profile, firm, notifications, data/privacy, team) | P1 | M | M3-T11 |
| M5-T07 | **Product analytics** (PostHog/Amplitude) + event taxonomy | P1 | S | — |
| M5-T08 | In-app **feedback** capture | P2 | XS | M5-T07 |
| M5-T09 | **Feature flags** (e.g. for staged rollouts) | P2 | S | — |
| M5-T10 | Edit/correct extracted client & alert data (trust + data quality) | P1 | M | M2-T07 |
| M5-T11 | Legal: ToS, Privacy Policy, DPA, cookie consent | P0 | S | — |
| M5-T12 | Backups + tested restore; data export (portability) | P0 | M | M1 |

**Checklist**
- [ ] Every state-changing action recorded in an immutable audit log
- [ ] Data residency documented; DSAR + erasure + export work
- [ ] Transactional emails send reliably; notifications surface in-app
- [ ] Analytics events flowing; feedback capture live
- [ ] Users can correct mis-extracted data
- [ ] Legal docs published; backups restore-tested

---

## M6 — AI Experience  ·  Priority P1/P2  ·  Effort ~L  ·  Deps: M2 (services + async jobs)

> From `PROJECT_REVIEW.md` §3.2, §4, §11 (High/Future). **This is "Prompt 6"** — improve the agent itself.

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M6-T01 | **Conversational** Ask Jarvis: persistent threads + history (DB-backed, tenant-scoped) | P1 | M | M1, M2-T07 |
| M6-T02 | **Streaming** responses (SSE/websocket) + token-level UI | P1 | M | M2-T05 |
| M6-T03 | **Context management**: conversation memory + relevant-history selection within token budget | P1 | M | M6-T01 |
| M6-T04 | Prompting overhaul: structured outputs / function-calling (replaces brittle parsing); per-firm tone/guardrails | P2 | M | M2-T12 |
| M6-T05 | **Retry logic** + graceful degradation for LLM/embedding/vector failures | P1 | S | M2-T08 |
| M6-T06 | **Long-running jobs**: progress updates + cancellation for ingestion/bulk ops | P1 | M | M2-T05 |
| M6-T07 | **Human-approval checkpoints** for any agent action that sends/writes (drafts → review → send) | P1 | M | M7-T01 |
| M6-T08 | Provenance / "why am I seeing this?" + confidence signaling on synthetic alerts & answers | P2 | M | M6-T01 |
| M6-T09 | Prompt-injection mitigation for ingested-document content fed to the LLM | P1 | M | M2-T07 |
| M6-T10 | Client **memory / longitudinal timeline** per client | P3 | L | M6-T03 |

**Checklist**
- [ ] Ask Jarvis is a real conversation (history + follow-ups + streaming)
- [ ] LLM failures retry/degrade gracefully; no silent empty answers
- [ ] Long jobs show real progress and can be cancelled
- [ ] No agent action that sends/writes happens without explicit human approval
- [ ] Document-sourced content can't hijack the system prompt
- [ ] Answers/alerts show provenance

---

## M7 — Close-the-Loop & Integrations  ·  Priority P1/P2  ·  Effort ~XL  ·  Deps: M1, M2, M6-T07

> From `PROJECT_REVIEW.md` §4 ("dead end"), §6 (wedge), §11 (High). Makes the product *actually proactive* and removes manual upload.

| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M7-T01 | **Send / log emails** (or hand-off to mail client) with audit trail + status | P1 | M | M5-T01, M5-T04 |
| M7-T02 | **Tasks** (create/assign/complete) + **calendar** events from alerts | P1 | M | M2-T07 |
| M7-T03 | **Scheduler / background worker**: genuinely proactive — morning digest email + auto pre-meeting briefs before meetings | P1 | L | M2-T05, M5-T04 |
| M7-T04 | First **calendar integration** (Google + Microsoft) | P1 | L | M1 |
| M7-T05 | First **CRM integration** (Intelliflo/Plannr/Wealthbox) with read + write-back | P1 | XL | M1, M2-T05 |
| M7-T06 | Consumer-Duty **MI dashboard** (4 PRIN 2A outcomes) + exportable evidence pack | P2 | L | M5-T01 |
| M7-T07 | Bulk operations (multi-client briefs, batch chase emails) | P2 | M | M7-T01 |

**Checklist**
- [ ] Adviser can act (send/task/calendar) from within the app, logged
- [ ] Scheduled digests + auto briefs fire on real time (not a manual slider)
- [ ] Calendar connected; at least one CRM syncs both ways
- [ ] Consumer-Duty evidence exportable

---

## M8 — Production Readiness & Final Polish  ·  Priority P0/P1  ·  Effort ~L  ·  Deps: all prior

> From `PROJECT_REVIEW.md` §12. **This is "Prompts 7 & 8."** Produce `RELEASE_CHECKLIST.md` as the output artifact.

### Hardening (Prompt 7)
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M8-T01 | Bug sweep across every user flow (auth, billing, ingestion, chat, brief, alerts, settings) | P0 | M | — |
| M8-T02 | Test suite: pytest (services/API), RTL (components), **Playwright e2e** (critical flows); wire into **CI** | P0 | L | M2-T07 |
| M8-T03 | Performance pass (DB query/index review, N+1s, payload sizes, frontend bundle, cold-start) | P1 | M | M2 |
| M8-T04 | Accessibility audit (axe + manual keyboard) to WCAG AA | P1 | M | M3-T13 |
| M8-T05 | SEO/metadata for marketing pages (titles, OG, sitemap, robots) | P2 | S | M3-T14 |
| M8-T06 | Deployment readiness: env/secrets mgmt, security headers/CSP, HTTPS, health checks, staging env, rollback | P0 | M | — |
| M8-T07 | Dependency & vuln audit gate (Dependabot/`npm audit`/`pip-audit`) in CI | P0 | S | M8-T02 |
| M8-T08 | Produce **`RELEASE_CHECKLIST.md`** | P0 | S | M8-T01..07 |

### Polish (Prompt 8)
| ID | Task | Pri | Effort | Depends on |
|----|------|-----|--------|-----------|
| M8-T09 | Copywriting pass (no "demo" language; consistent voice) | P1 | S | — |
| M8-T10 | Animations/micro-interactions audit (defined curves/durations; reduce gratuitous) | P2 | S | M3-T04 |
| M8-T11 | Success/error message consistency | P2 | XS | M2-T15 |
| M8-T12 | Mobile responsiveness final sweep | P1 | S | M3-T01 |
| M8-T13 | Keyboard accessibility final sweep | P1 | S | M8-T04 |
| M8-T14 | **Dark mode** (token-driven) | P2 | M | M3-T02 |
| M8-T15 | Consistency sweep (spacing, icons, empty/loading skeletons) | P1 | S | M3 |

**Checklist**
- [ ] Every critical flow walked through; bugs filed/fixed
- [ ] CI green: pytest + RTL + Playwright e2e + dependency audit
- [ ] Perf budget met; a11y AA; SEO basics on marketing pages
- [ ] Staging + rollback + health checks + security headers in place
- [ ] `RELEASE_CHECKLIST.md` produced and satisfied
- [ ] Polish: copy, animations, messages, dark mode, consistency done

---

## Dependency graph (high level)

```
M0 ──► M1 ──► M2 ──► M3(full) ──► M5 ──► M7 ──► M8
        │      │        ▲          ▲       ▲
        │      │        │          │       │
        │      └──► M4 ─┘          │       │
        │      └──► M6 ────────────┘       │
        │                                  │
        └──► M3(early: T01–T03) ───────────┘   (responsive shell can start right after M0)
```

- **M1 blocks almost everything** (tenant context).
- **M2 (Redis, async jobs, API client, types)** unblocks M3-full, M4, M6.
- **M4 entitlements** unblock feature gating used across M5/M6/M7.
- **M6-T07 (approval checkpoints)** blocks M7 send/write actions.

---

## Launch gate (definition of done for paid launch)

Ship **only** when every P0 below is ✅:

- [ ] **M0** complete (no anonymous data access/wipe; cost-abuse capped)
- [ ] **M1**: auth + multi-tenancy + RLS proven isolated; roles enforced
- [ ] **M2**: Redis cache, async ingestion, connection pool, Sentry, structured logs, paginated lists, shared API client/types
- [ ] **M3-T01**: fully responsive (mobile usable on every page) + designed empty/loading/error states (M3-T06/07/08)
- [ ] **M4**: Stripe billing + entitlements + per-workspace usage limits enforced
- [ ] **M5**: audit log, data residency, DSAR/erasure/export, legal docs, backups restore-tested
- [ ] **M8**: bug sweep, CI with e2e tests, deployment readiness (headers/HTTPS/staging/rollback), `RELEASE_CHECKLIST.md`

**Explicitly OK to trail launch (P2/P3):** live meeting capture, CRM write-back (start with one), automation builder, marketplace, dark mode, enterprise SSO/SAML, ISO 27001/SOC 2 (start the *process* early, certification later), client memory/timeline, advanced analytics/MI.

---

## Suggested calendar (1 engineer; compresses with more)

| Weeks | Focus |
|-------|-------|
| 0 (day 1) | M0 |
| 1–3 | M1 + M3 early slice (T01–T03) |
| 3–6 | M2 |
| 5–8 | M4 (overlaps tail of M2) |
| 6–10 | M3 full overhaul |
| 9–13 | M5 |
| 11–15 | M6 |
| 14–22 | M7 (integrations are the long pole) |
| ongoing / 20–24 | M8 hardening + polish → release |

> This mirrors the team workflow in the brief: **Research/Audit → Plan → (foundations) → UI → Architecture → Features → AI → Hardening → Polish/Release**, with the one sequencing tweak called out at the top (foundations before the full UI rebuild).

---

## Next agent runs (mapping to your prompts)

- **Prompt 3 (UI/UX):** execute **M3** (start with the early slice already, full overhaul after M2).
- **Prompt 4 (Architecture):** execute **M2** (no new features).
- **Prompt 5 (SaaS features):** execute **M1 → M4 → M5** (auth/tenancy is the foundation feature).
- **Prompt 6 (AI experience):** execute **M6**.
- **Prompt 7 (Production readiness):** execute **M8** hardening → produce `RELEASE_CHECKLIST.md`.
- **Prompt 8 (Final polish):** execute **M8** polish slice.

When starting a run, reference the milestone and task IDs (e.g. "implement M2-T02 and M2-T05") so changes stay focused and reviewable.
