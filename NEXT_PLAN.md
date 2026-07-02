# KritiFin — Project Status & Next-Step Plan

_Last updated: 2 Jul 2026_

This is the living planning document for **KritiFin (Proactive Financial Agent)** — a proactive AI workspace for UK financial advisers. It captures current status, what's done, what remains, priorities, technical debt, known issues, risks, and the implementation roadmap. Historical milestone context lives in [`docs/planning/`](docs/planning/).

---

## 1. Current Status (at a glance)

| Dimension | State |
|-----------|-------|
| **Maturity** | Late-stage MVP / advanced prototype — broad, coherent feature set |
| **Production-ready?** | Not for real client PII. Ready for internal testing and controlled beta with synthetic data |
| **Stack** | Next.js 14 + TS + Tailwind + React Query · FastAPI (Python 3.9+) · Postgres (Supabase) · Qdrant · OpenAI |
| **Deployment** | Vercel (frontend) + Render (backend) + Supabase + Qdrant Cloud |
| **Tests** | ~18 backend pytest suites (~100 test fns) · 6 Playwright specs (chromium/firefox/webkit/mobile) |
| **Tenancy** | Single-tenant (⚠️ `adviser_id`/RLS not enforced) |
| **Biggest blocker to launch** | Multi-tenancy + row-level security + durable audit |

---

## 2. Completed Work

### Product features (verified in code)

| Area | Feature |
|------|---------|
| **Dashboard** | Pulse, KPIs, priority timeline, spotlight, morning AI digest, draft email, mark done, completed list, load sample data |
| **AI Copilot** | Hybrid RAG + structured data, client scoping, citations, follow-up chips, `?q=` auto-ask deep link |
| **Meeting Brief** | Auto-generate, talking points, source list, regenerate, `?clientId=&auto=1` deep link |
| **Client 360** | Client list + detail, book analytics, playbooks + apply, review notes, client edit |
| **Ingestion** | PDF/DOCX upload, async jobs, transcript ingest, note templates, duplicate detection, compliance scan |
| **Compliance** | Vulnerability + Consumer Duty scan (FG21/1), AI audit log, human-review approval gate, data posture |
| **Settings** | Clear data, export data, audit view, posture display |
| **Auth** | Supabase login/signup, JWT verification (ES256 via JWKS, HS256 fallback), graceful degradation |

### Platform / engineering

- Centralized backend services: `llm`, `prompts`, `rag_context`, `safety`, `alert_helpers`, `cache`, `audit`, `jobs`, `analytics`, `playbooks`, `posture`, `export`.
- Connection pooling with **IPv4/DNS64 stall mitigation** (`db.py` `_force_ipv4`).
- TTL caching (brief 1h, draft 30m, chat 5m, digest 60s, structured ctx 90s, extraction 24h); parallel embed + DB on cache miss.
- Security: per-IP rate limiting, input clamping, RAG prompt-injection sanitization, magic-byte upload validation, safe redirects, CSP + security headers, constant-time API-key compare.
- Frontend: shared API client + typed hooks, `PageShell`/UI library, lazy-loaded modals, memoized cards, nav prefetch, AI component set with citations/trust footer.
- Docs: README, `FEATURES_AND_IMPLEMENTATION.md`, `DEPLOYMENT.md`, `docs/` (demo script, AI/security/perf guides, QA report, planning archive), MIT `LICENSE`.

---

## 3. Partially Completed

| Feature | Gap |
|---------|-----|
| **Authentication** | Optional + single-tenant; no password reset, no enforced email verification, no session→tenant binding |
| **Audit trail** | In-memory ring buffer (500 entries) — not durable; unusable as a real FCA record |
| **Async ingestion** | In-process `BackgroundTasks` + in-memory job registry; no broker/worker; lost on restart |
| **Data posture** | Reports retention/encryption/residency but nothing *enforces* them |
| **Export** | No per-tenant scoping or DSAR workflow |
| **Book analytics** | Adviser-facing only; no **product** analytics instrumentation |

---

## 4. Remaining / Missing Features

- **Tenant/workspace model** — `workspaces`/`users`/`memberships` tables + RLS policies.
- **Durable conversation persistence** per user/tenant.
- **Outbound actions** — real email send + logging; in-app/email notifications.
- **Scheduled proactivity** — cron digests, auto pre-meeting briefs (delivers on the "proactive" promise).
- **CRM/calendar integration** — Intelliflo / Outlook / Google (removes manual-upload friction).
- **Observability surfaces** — error dashboard, usage metrics, deep health check.

---

## 5. Priorities

### P0 — Critical (before any real customer data)
1. **Multi-tenancy + Postgres RLS** (workspaces/users/memberships; enforce tenant on every query).
2. **Durable, tenant-scoped, append-only audit trail** (move audit → Postgres).
3. **Enforce auth by default in production** (fail closed).
4. **Error + uptime monitoring** (Sentry backend+frontend; uptime check; deep `/health`).
5. **CI pipeline** (lint, typecheck, build, backend pytest, Playwright on mock).

### P1 — High
6. Product analytics (PostHog: activation, funnels, feature adoption).
7. Durable async ingestion (real queue/worker; persist jobs).
8. Shared cache → Redis (multi-instance).
9. Cold-start mitigation (keep-warm / paid Render tier).
10. Streaming AI responses (digest/brief/chat).
11. Password reset + email verification.

### P2 — Medium
- Scheduled proactive digests (cron → email).
- Real email send + logging.
- Surface compliance/analytics as first-class navigation.
- Accessibility audit + fixes.
- Published API docs + data-flow/threat model.

### P3 — Future
- CRM/calendar integrations · conversational memory · teams/RBAC · Stripe billing · DSAR/retention automation.

---

## 6. Technical Debt

| Debt | Impact | Severity |
|------|--------|----------|
| In-memory cache/audit/jobs | Blocks horizontal scale; loses audit/jobs on restart | High |
| No multi-tenancy / RLS | Blocks multi-customer launch | Critical |
| No CI pipeline | Silent regressions; manual testing | High |
| No Dockerfile / reproducible build | Env drift local↔Render | Medium |
| CORS `allow_credentials=True` + `*` methods/headers | Overly permissive; tighten before real auth | Medium |
| Python 3.9 compat relies on `from __future__ import annotations` | Fragile; pin runtime | Medium |
| Schema/code drift (`alerts.type` comment vs `FOLLOW_UP`/synthetic types) | Onboarding confusion | Low |

---

## 7. Known Issues

- **Cold starts** on Render free tier → first request appears to fail ("check the backend is running").
- **API open by default** when neither `API_KEY` nor Supabase auth is configured (dev convenience, prod risk).
- **AI latency** on digest/brief not masked by streaming; can feel slow.
- **Local dev port coupling** — frontend `NEXT_PUBLIC_API_URL` must match backend port; `npm run sync-env` provided to reduce mismatch.
- **Auth-mode E2E split** — Playwright assumes demo mode; real-auth runs need `E2E_EMAIL`/`E2E_PASSWORD`.

---

## 8. Risks (ranked)

| # | Risk | Type | Severity | Mitigation |
|---|------|------|----------|-----------|
| 1 | Cross-customer data exposure (no isolation) | Security/Regulatory | Critical | P0 multi-tenancy + RLS |
| 2 | In-memory audit → no durable FCA record | Regulatory | Critical | Persist audit to DB |
| 3 | API open by default | Security | High | Enforce auth in prod |
| 4 | No monitoring → blind to outages | Reliability | High | Sentry + uptime |
| 5 | In-memory cache/jobs → no horizontal scale | Scalability | High | Redis + durable jobs |
| 6 | Cold starts → poor first impression | Product/Perf | Medium | Keep-warm / paid tier |
| 7 | No CI → regressions | Technical | Medium | CI gate |
| 8 | LLM cost/latency/failure | Business/Perf | Medium | Caching (present) + fallbacks + budgets |
| 9 | Manual ingestion → low adoption | Product | Medium | Integrations (P3) |

---

## 9. Success Metrics (to instrument)

| Category | Metric | Beta target |
|----------|--------|-------------|
| Activation | % new advisers who ingest ≥1 doc AND run ≥1 Copilot query in first session | ≥60% |
| Activation | Time-to-first-brief | <10 min |
| Retention | Weekly active advisers W4 | ≥40% |
| Adoption | % using compliance scan | ≥30% |
| Performance | p95 Copilot latency (streamed: first token) | <6 s (<2 s) |
| Reliability | Uptime | ≥99.5% |
| Errors | 5xx / total | <0.5% |
| Satisfaction | NPS | ≥30 |

_None are measurable today — instrumentation (P1) is the prerequisite._

---

## 10. Implementation Roadmap

### Next sprint (2 weeks) — "Safe for real advisers"
Order: (1) multi-tenancy schema + RLS → (2) enforce auth-by-default → (3) tenant-scope all queries → (4) durable audit → (5) Sentry → (6) uptime + deep health → (7) CI → (8) PostHog → (9) cold-start fix → (10) password reset + verification.

- **Quick wins:** Sentry, uptime, CI, PostHog, cold-start (each ≤2 days).
- **High-risk:** items 1–4 (data-model migration + RLS; migrate audit last).
- **Postpone:** CRM integrations, billing, streaming, scheduled digests.

### 30-day plan
- **W1:** Multi-tenancy schema + RLS design/migration; auth-by-default; Sentry + uptime.
- **W2:** Tenant-scope queries; migrate audit → Postgres; stand up CI.
- **W3:** PostHog + funnels; cold-start mitigation; password reset/verification.
- **W4:** Streaming responses; tighten CORS; a11y quick-fixes; invite 3–5 design-partner advisers (synthetic data).

### 90-day roadmap
- **Month 1 — Foundation & trust:** P0 complete; controlled beta; metrics flowing.
- **Month 2 — Reliability & insight:** Redis cache + durable async jobs; streaming everywhere; API/data/threat docs; a11y pass; expand beta (~20 advisers).
- **Month 3 — Proactivity & wedge:** Scheduled proactive digests + real email send; deepen compliance co-pilot (exportable Consumer Duty evidence); first CRM/calendar integration; Stripe billing; first paying customers on a compliance-led offer.

---

## 11. Strategic Notes

- **Highest-impact next step:** ship multi-tenancy + RLS + enforced auth — converts a single-user demo into a product that can safely hold more than one customer's data.
- **Biggest opportunity:** own the **"Consumer Duty / vulnerability compliance co-pilot"** category for UK IFAs. Lead GTM with compliance, not "AI chat."
- **Do not** add net-new features until the trust foundation (isolation, durable audit, monitoring) exists.
