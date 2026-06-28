# Project Review — Proactive Financial Agent (Jarvis)

> **From hackathon demo to production-ready SaaS — a senior product/engineering/design audit.**
>
> Review date: 28 Jun 2026 · Reviewed at commit `ba481e1` (branch `master`)
> Method: full codebase read (backend + frontend), competitor & UX research, and a live Playwright UI audit (screenshots in [`review-screenshots/`](review-screenshots/)).

---

## Table of contents

1. [Executive Summary](#1-executive-summary)
2. [Current Project Assessment](#2-current-project-assessment)
3. [UI Review](#3-ui-review)
4. [UX Review](#4-ux-review)
5. [Authentication Review](#5-authentication-review)
6. [Competitor Analysis](#6-competitor-analysis)
7. [SaaS Readiness Score](#7-saas-readiness-score)
8. [Technical Debt](#8-technical-debt)
9. [Code Quality Review](#9-code-quality-review)
10. [Security Review](#10-security-review)
11. [Recommended Features](#11-recommended-features)
12. [Launch Checklist](#12-launch-checklist)
13. [Product Roadmap](#13-product-roadmap)
14. [Immediate Action Items](#14-immediate-action-items)
15. [Screenshots](#15-screenshots)
16. [Final Recommendations](#16-final-recommendations)

---

## 1. Executive Summary

**What this is today:** A well-crafted, single-user *demo* of a proactive assistant for UK financial advisers (IFAs). An adviser uploads fact-finds / meeting notes (PDF/DOCX); an LLM extracts a client profile and a set of dated "alerts" (reviews, deadlines, birthdays, follow-ups) into Postgres, and the same text is chunked into Qdrant for retrieval. The UI then presents a dashboard of priorities, a hybrid RAG chat ("Ask Jarvis"), pre-meeting briefs, an alerts list, and one-click LLM-drafted emails. A "simulate date" control lets you time-travel to show what *would* be due.

**The honest verdict:** This is a strong **hackathon submission** and a genuinely good demonstration of a hybrid (structured + vector) retrieval architecture with thoughtful caching. It is **not** a product you could sell. The single biggest gap is existential: **there is no authentication, no concept of a user or account, and no tenant isolation whatsoever.** Every byte of data is global and every API endpoint is public — including one that wipes the entire database with no auth. For a tool whose entire purpose is to store sensitive UK client financial data (and, per FCA/ICO guidance, potentially *special-category* vulnerability data), that is disqualifying for any commercial launch.

**Would people pay for it today? No** — not because the idea is weak (it is good and the domain understanding is real), but because:

- It cannot have customers (no accounts, no isolation, no billing).
- It is not actually "proactive" in the autonomous sense — it is a read-time dashboard plus a manual time-travel slider. Nothing fires, schedules, notifies, or sends.
- It requires advisers to *manually upload documents*, while market leaders (Jump, Zocks, Mili) capture meetings live and write back into the CRM the adviser already uses.
- It is desktop-only in practice (the layout is broken on mobile).

**The opportunity:** The market is real and growing (Jump claims 31,000+ advisers; per-seat pricing is $79–$150/mo). The differentiated wedge here is **UK-native compliance** (Consumer Duty review-overdue, FCA/ICO vulnerability handling, UK data residency) — an angle the US-built incumbents under-serve. But realizing it requires re-platforming from "demo" to "multi-tenant SaaS": auth + tenancy, async/event-driven proactivity, CRM integrations, billing, and a compliance/security posture (RLS, audit trails, UK data residency, DSAR).

**Bottom line:** Keep the architecture and the domain logic; treat the rest as a v0 to be hardened. The roadmap in §13 sequences this into Critical → High → Medium → Future. The single most important next step is in §14.

---

## 2. Current Project Assessment

### 2.1 Architecture (as built)

```
Next.js 14 (Pages Router, TS, Tailwind)        FastAPI (Python 3.12)
  pages/ index, chat, brief, admin, alerts, settings        routers/ ingest, monitor, chat, settings
        │  fetch(NEXT_PUBLIC_API_URL)  ─────────────────────►  services/ llm_extractor, vector_store, cache, config
        │                                                          │
        ▼                                                          ├──► Postgres (Supabase): clients, alerts, ingested_documents
   (no auth, no session)                                           ├──► Qdrant: collection `client_memory` (1536-d, cosine)
                                                                   └──► OpenAI: gpt-4o (chat/draft/extract), gpt-4o-mini (brief),
                                                                            text-embedding-3-small
```

**Components**
- **Frontend:** Next.js 14.2.15 (Pages Router), TypeScript, Tailwind. Six pages, a `LayoutContext` for the page title/header, and three components (`AppLayout`, `AlertCard`, `DraftEmailModal`, `DateSimulator`). Every page calls the backend with raw `fetch` against `NEXT_PUBLIC_API_URL`.
- **Backend:** FastAPI with four routers. `db.py` opens a **new psycopg2 connection per request**. An **in-memory, per-process dict cache** (`services/cache.py`) backs chat/brief/draft/extraction TTLs.
- **Data model (`backend/supabase_schema.sql`):** `clients`, `alerts`, `ingested_documents`. There is a nullable `clients.adviser_id UUID` column, but it is populated only from a single global env var `ADVISER_ID` and is **never used in any query filter**. There is **no `users`, `advisers`, `accounts`, `workspaces`, or `subscriptions` table.**
- **Vector store:** one shared Qdrant collection; payload carries `client_id`, `client_name`, `doc_type`, `date`, `document_id`, `filename`, `source_type`, `ingested_at`.

### 2.2 How the "proactive agent" actually works

This is important to be precise about, because the README frames it as an agent that acts "at the right moment." In reality:

- **Ingestion (`routers/ingest.py` → `services/llm_extractor.py`):** On upload, text is extracted (PyMuPDF/python-docx), sent to GPT-4o with a detailed UK fact-find prompt, and parsed into `{client, alerts}`. Alerts get a `trigger_date` and a `type` ∈ {DEADLINE, OPPORTUNITY, COMPLIANCE, FOLLOW_UP}. This runs **synchronously inside the HTTP request**.
- **"Proactivity" (`routers/monitor.py`):** The dashboard calls `GET /pulse?simulated_date=…` which returns alerts whose `trigger_date` falls in `[simulated_date, +30d]`, plus *synthetic* `REVIEW_OVERDUE` alerts computed on the fly for clients with `last_review_date` older than 365 days (a nice Consumer-Duty touch).
- **The catch:** Nothing is event-driven. There is **no scheduler, no background worker, no notification channel, and no email actually sent** (emails are LLM-*drafted* and copied to the clipboard). The "right moment" is whatever date the user manually drags the simulator to. So "proactive" today = "a read-time prioritized list + a demo time-machine." That is a fine demo, but it is not autonomous behavior.

### 2.3 What is genuinely good (keep this)

- **Hybrid retrieval** (structured Postgres context + Qdrant RAG) is the right pattern for this domain and is implemented cleanly in `routers/chat.py`.
- **Thoughtful latency work:** chat caches responses by normalized query hash, caches structured context for 90s, and runs the DB fetch + embedding **in parallel** on cache miss (`ThreadPoolExecutor`). This is more sophisticated than most hackathon code.
- **Duplicate detection** by SHA-256 content hash in `ingested_documents`.
- **Real domain understanding:** Consumer-Duty review-overdue, "waiting on client" follow-ups, UK date-format parsing, talking-point generation for briefs.
- **Consistent, modern desktop visual language** (Inter, restrained palette, card system) — see §3.

### 2.4 Incomplete / missing features (high level)

| Area | State |
|------|-------|
| Authentication / accounts | **Absent** |
| Multi-tenancy / data isolation | **Absent** (all data global) |
| Onboarding | **Absent** (drops you straight onto an empty dashboard) |
| Billing / pricing / plans | **Absent** |
| Teams / roles / sharing | **Absent** |
| Notifications / email send / scheduling | **Absent** (draft-only) |
| CRM integrations (Intelliflo, etc.) | **Absent** (manual upload only) |
| Mobile responsiveness | **Broken** (see §3.6) |
| Automated tests | **Absent** (only manual `scripts/test_*.py`) |
| Observability / error reporting | **Absent** |
| Settings | Effectively one destructive button |
| Landing / marketing site | **Absent** |

---

## 3. UI Review

The desktop UI is the project's strongest non-architectural asset: clean, consistent, and clearly inspired by Linear/Stripe (per `frontend/DESIGN_SYSTEM.md`). The problems are (a) it is **desktop-only**, (b) there are **no designed empty / loading / error states**, (c) **inconsistencies** between pages, and (d) it reads as a **demo** rather than a product (no brand, no account, copy that literally says "demo").

> Screenshots referenced below live in [`review-screenshots/`](review-screenshots/) (desktop = 1440px, mobile = 390px).

### 3.1 Dashboard — `dashboard-desktop.png`

**Looks decent:** clear KPI row, "Start here" priority list, Pulse cards, "Alerts over time" mini-bar table, and two tables.

Problems & why they matter:
- **Too many competing sections, no visual rhythm.** "Start here", "Overdue follow-ups", 4 KPIs, "Pulse" (cards), "Alerts over time", "Recent alerts" (table), "Recently completed" (table) all stack as equal-weight blocks. The user's eye has no anchor. *Fix:* establish a 2-column grid (primary work queue left, KPIs/insights right), collapse "Recent alerts" and "Pulse" — they are the **same data shown twice** (cards + table), which is redundant and confusing.
- **KPI cards are decorative, not actionable.** "Total alerts / High risk / Upcoming deadlines / Clients" are vanity counters with custom CSS tooltips. *Fix:* make each KPI a filter entry-point (click "High risk" → filtered Alerts view) and add trend/delta context ("3 due this week").
- **Tooltips are hand-rolled** absolutely-positioned divs duplicated four times (verbose, fragile, and they also duplicate the native `title` attribute). *Fix:* one reusable `Tooltip` component.
- **"Draft email" everywhere, "Mark done" only sometimes.** Action affordances are inconsistent across the four places alerts appear.

### 3.2 Ask Jarvis — `chat-desktop.png`, `chat-answer-desktop.png`

**Looks good** — this is the most polished screen. Suggestion chips, a tidy answer card with Markdown, and a sources list.

Problems:
- **It is single-shot Q&A, not a conversation.** Each ask **replaces** the previous answer (`setAnswer(null)` then set). There is no history, no follow-up, no streaming — which is jarring versus every modern AI product (ChatGPT/Claude/Perplexity). *Fix:* a real chat transcript with streamed tokens and follow-ups.
- **39 hard-coded suggestion prompts** (`SUGGESTIONS_POOL`) — many promise analytics the backend can't actually do ("conversion rates by referral source", "revenue vs time to service"). This over-promises and will produce "I don't have that data" answers. *Fix:* curate to what the data supports; generate suggestions from the user's actual book.
- **No loading skeleton for the answer** — there's a nice custom "Jarvis is thinking" card, but it doesn't match the answer layout (Linear/Stripe principle: skeletons should match the content they replace).
- **Centered max-w-2xl column** wastes the wide canvas; sources could sit in a right rail.

### 3.3 Pre-meeting brief — `brief-generated-desktop.png`

- **Markdown hierarchy is collapsing.** The brief renders `## Heading` then bullets with very tight spacing, so "Key facts / Upcoming items / Commitments" don't read as distinct sections. *Fix:* tune the prose styles (more vertical rhythm, clearer h2/h3).
- **"Download as PDF" opens a `window.open` + `document.write` print hack.** Functional, but it can be blocked by popup blockers and produces inconsistent output. *Fix:* server-side PDF or a proper client PDF lib.
- **No multi-client / batch briefs**, no "email me my briefs the morning of meetings" — which is the actual job-to-be-done.

### 3.4 Ingestion — `ingestion-desktop.png`

- **The 3-step progress animation is fake.** `frontend/pages/admin.tsx` advances "Uploading → Extracting → Indexing" on `setTimeout(800ms/2200ms)` regardless of real backend progress. For a 20-second LLM extraction this lies to the user and then jumps. *Fix:* stream real progress (SSE/websocket) from an async ingestion job.
- **No file size guidance, no max-size, no per-file remove/retry.** Stored documents list has no delete/re-ingest action.
- **Dropzone emoji (📄)** and emoji icons in `AlertCard` (💰 ⚠️ 📋 📌) read as informal for a compliance tool. *Fix:* a consistent icon set (e.g. Lucide).

### 3.5 Alerts — `alerts-desktop.png`

- **Raw enum strings leak to users.** Type column shows `FOLLOW_UP` and `REVIEW_OVERDUE` verbatim, while the **dashboard humanizes the same values** ("Waiting on client", "Review overdue"). Direct inconsistency between two pages. *Fix:* one shared label/format map.
- **Filters don't persist** in the URL; refresh resets them. No empty-state guidance beyond one line. No pagination (the list is unbounded — see §8).

### 3.6 Mobile — `*-mobile.png` (CRITICAL)

**The app is unusable on mobile.** `AppLayout` renders a fixed `w-60` (`flex-shrink-0`) sidebar with **no responsive behavior, no hamburger, no drawer**. On a 390px viewport the sidebar eats 240px and the content is crushed into ~150px — the dashboard mobile screenshot is essentially a sliver of unreadable content. This affects **every page**. *Fix:* collapse the sidebar into a top bar + drawer below `md:`, and audit each page's grids for mobile reflow.

### 3.7 Settings — `settings-desktop.png`

- **A near-empty page** whose first sentence says *"No in-app settings are needed for this demo."* This is the clearest "this is a hackathon, not a product" tell in the UI. The only control is a destructive **"Clear all data"**. *Fix:* a real settings area (profile, firm, integrations, notifications, billing, data/privacy) — see §11.

### 3.8 Cross-cutting UI issues

- **No design tokens for color/spacing** beyond Tailwind defaults; `sky-600` is hard-coded as the brand color in dozens of places. *Fix:* a small token layer (CSS vars / Tailwind theme) so the brand can change in one spot.
- **No favicon/brand** beyond a "J" square; `_document.tsx` has only a meta description; no Open Graph, no title template.
- **Inconsistent button paddings/casing** ("Draft email" vs "Draft Email" vs "Ask").
- **Accessibility:** generally uses semantic elements and `aria-label`s on the date picker/modal (good), but: modals lack focus-trapping and `role="dialog"`/`aria-modal` on the email modal; color-only status encoding; no skip-link; chips are buttons (good) but the answer region isn't `aria-live`. Needs a pass against WCAG AA.

---

## 4. UX Review

- **No onboarding, no activation path.** A first-time user lands on an empty dashboard that says "No priorities yet. Upload documents in Ingestion *or run the seed script*." Referencing a *seed script that does not exist in the repo* is a broken promise. Per 2026 best practice, the **empty state should be the onboarding** (one clear CTA, "load sample data", and copy that teaches the mental model). *Fix:* a guided first-run: connect/upload → see your first alerts → ask your first question, plus a one-click sample dataset.
- **The core loop has a dead end.** The product's promise is "act at the right moment," but the only action is *draft an email and copy it to your clipboard.* There is no send, no log, no task, no calendar event, no CRM write-back. The user does the actual work elsewhere, so the tool doesn't close the loop or earn a place in the daily routine.
- **State doesn't carry across pages.** The "Simulate date" is independent on Dashboard vs Alerts; navigating loses context and refetches everything.
- **No conversation memory** in Ask Jarvis (see §3.2).
- **Trust & transparency gaps.** For a tool making compliance-adjacent claims, there's no "why am I seeing this?" provenance on synthetic alerts, no confidence/uncertainty signaling, and no way to correct a mis-extracted client/alert. Advisers will not trust a black box over their book.
- **Error UX is technical.** Failures surface raw strings like "Failed: 500" / "Monitor API not found." *Fix:* human-voiced, recoverable error states.
- **Destructive action is under-protected** (text confirm only; no "type DELETE", no auth) — and it's the *only* settings feature.

---

## 5. Authentication Review

**Finding: there is no authentication or authorization of any kind. This is the project's most critical gap.**

| Question | Finding |
|----------|---------|
| Which auth provider is used? | **None.** No NextAuth/Clerk/Supabase Auth/Auth0; no login or signup page exists. |
| Is auth implemented at all? | **No.** `_app.tsx` wraps pages in a layout only; no session, token, or guard anywhere. |
| Is session handling secure? | **N/A — there are no sessions.** CORS sets `allow_credentials=True` but no credentials are ever sent. |
| Do protected routes exist? | **No.** Every page and every API route is public. |
| Is authorization handled? | **No.** No roles, no ownership checks; `clients.adviser_id` exists but is never filtered on. |
| Is onboarding complete? | **No onboarding exists.** |
| Security concerns? | **Severe — see below.** |

**Concrete consequences (all reproducible against the running backend):**

1. **Anyone can read all data.** `GET /api/monitor/clients`, `/pulse`, `/alerts`, and `POST /api/chat` return every client's sensitive financial data to any unauthenticated caller.
2. **Anyone can destroy all data.** `POST /api/settings/clear-data` (`routers/settings.py`) deletes every row in `alerts`, `clients`, `ingested_documents` and **drops + recreates the Qdrant collection** — with **no authentication**. A single curl wipes the system.
3. **Anyone can run up your OpenAI bill.** `POST /api/ingest/upload`, `/api/chat`, `/api/chat/brief`, `/api/monitor/draft-email` all call paid LLM APIs with **no auth and no rate limiting** — a direct cost-abuse / DoS vector.
4. **No tenant boundary.** Even if you added login tomorrow, the data model has nowhere to scope data to a user/firm. This is a schema-level problem, not just a middleware one.

**Required (minimum) to make this a product:**
- An identity layer. Given the stack, **Supabase Auth + Postgres RLS** or **Clerk Organizations** are the pragmatic choices (both surfaced repeatedly in current SaaS architecture guidance).
- A tenancy model: `users`, `firms`/`workspaces`, `workspace_members(role)`, and a `workspace_id` (or `adviser_id`) **on every domain table**, enforced by **RLS at the database level** (column checks alone are described in the literature as "a company-ending event" waiting to happen).
- Per-tenant scoping of the Qdrant payload filter and of every cache key (today's caches are keyed by `alert_id`/`client_id`/query-hash with no tenant prefix — they would cross-leak the moment you go multi-tenant).
- Protected API (auth dependency on every router) + protected frontend routes + a real session.

---

## 6. Competitor Analysis

The "AI for financial advisers" category matured fast in 2025–26. Standalone meeting-notetakers rebranded into "agentic operating systems" that sit above the adviser's stack, while CRMs shipped native AI defensively.

| Product | Core wedge | Pricing (approx) | Notable strengths | Relevance to us |
|---------|-----------|------------------|-------------------|-----------------|
| **Jump AI** | Meeting OS: live capture → CRM write-back → follow-ups | ~$100–150/seat/mo | 31k+ advisers, 30+ integrations, SOC 2, RBAC, configurable compliance | The benchmark. We lack live capture, integrations, and compliance posture. |
| **Zocks** | Audio-first notetaking, simpler/cheaper | ~$89+/seat/mo | Price, simplicity | Shows a lower-cost lane exists. |
| **Mili** | Multilingual capture | ~$79+/seat/mo | Strong non-English support | Niche differentiation by language. |
| **Saturn** | Next-gen advisor + prospect/social content | Custom | Prospecting + content | Differentiates on top-of-funnel. |
| **Zeplyn / CogniCor / Mercedes / Pulse360** | Meeting/admin automation | Varies | Various niches | Crowded middle. |
| **Wealthbox native AI / Altruist Hazel / Advisor360 Parrot / Altitude Pathfinder** | AI *inside* the CRM/system-of-record | Bundled | Deep data access, no integration tax | The biggest threat: AI bundled free where the data already lives. |

**Where our product stands vs the field**
- **Behind on:** live meeting capture, CRM write-back, integrations breadth, send/automation, team/compliance/security, mobile, and the fact that incumbents already have distribution.
- **Comparable on:** the *idea* of pre-meeting briefs and "surface the next best action" (Jump's "Meeting prep made easy / talking points" is essentially our brief feature).
- **Potentially ahead on (if we lean in):** **UK-native compliance**. The incumbents are overwhelmingly US-built; UK guidance (and vendors like Regure/FI Digital) make a strong case that US SaaS requires "heavy customisation" for FCA Consumer Duty, UK GDPR data residency (AWS `eu-west-2`), vulnerability (special-category) handling, DSAR/erasure, and immutable audit trails. Our Consumer-Duty review-overdue logic is a seed of this.

**Strategic takeaway:** Do not try to out-feature Jump on meeting capture. **Win a wedge: "the UK-compliance-native proactive layer for IFAs"** — deep Consumer Duty + FCA/ICO posture + Intelliflo/CRM integration — and integrate *with* the meeting tools rather than rebuilding them.

---

## 7. SaaS Readiness Score

Scored 0–10 per category (0 = absent, 10 = production-grade). Weighted to reflect launch-blocking severity.

| # | Category | Score | Notes |
|---|----------|:----:|-------|
| 1 | Authentication & identity | **0** | None exists. |
| 2 | Multi-tenancy & data isolation | **0** | All data global; no tenant column used; no RLS. |
| 3 | Authorization / roles | **0** | None. |
| 4 | Billing / subscriptions | **0** | None. |
| 5 | Feature gating / plans | **0** | None. |
| 6 | Rate limiting / usage limits | **0** | None — cost-abuse exposed. |
| 7 | Security posture | **1** | Secrets in env + .gitignore is the only positive; destructive open endpoint, known-vuln Next.js. |
| 8 | Onboarding & activation | **1** | Empty state references a non-existent seed script. |
| 9 | Observability / monitoring / error reporting | **0** | No logging framework, no Sentry, no metrics. |
| 10 | Testing & CI | **0** | No automated tests, no CI. |
| 11 | Email / notifications | **0** | Draft-only; nothing sent. |
| 12 | Integrations (CRM/calendar) | **0** | Manual upload only. |
| 13 | Mobile / responsiveness | **2** | Desktop good; mobile broken. |
| 14 | Core UX polish (desktop) | **6** | Genuinely good visual craft. |
| 15 | Architecture & data design | **5** | Good hybrid RAG; but in-proc cache, per-request connections, sync ingestion. |
| 16 | Compliance (FCA/GDPR) readiness | **1** | Stores sensitive PII with zero access control; no residency/audit/DSAR. |
| 17 | Documentation | **6** | README/DEPLOYMENT/FEATURES are thorough (for a demo). |

**Overall weighted readiness: ~1.5 / 10 — "Advanced prototype / demo."**
The desktop UI and the retrieval architecture are real assets; everything required to be a *commercial multi-tenant SaaS* is missing. This is expected for a hackathon — the score reflects distance to launch, not effort or talent.

---

## 8. Technical Debt

**Backend**
- **New DB connection per request** (`db.py: get_connection()` calls `psycopg2.connect(url)` every time). No app-level pool (relies entirely on Supabase's pooler); adds latency and risks connection exhaustion under load. `sqlalchemy` is in `requirements.txt` but **unused**.
- **In-memory, per-process cache** (`services/cache.py`). Breaks the moment you run >1 Uvicorn worker or >1 Render instance; lost on every restart/cold-start; not shared; will **cross-leak across tenants** once auth is added (keys aren't tenant-scoped). Needs Redis.
- **Synchronous ingestion in the request path.** `/api/ingest/upload` runs LLM extraction + embedding + Qdrant upsert inline; a large doc can exceed HTTP timeouts. Needs a job queue (e.g. RQ/Celery/Arq) + status polling/streaming.
- **Clients re-instantiated per call** — `QdrantClient(...)` and `OpenAI(...)` are constructed inside helper functions on every request (`_search_qdrant`, `upsert_to_qdrant`, `get_embeddings_openai`, `_synthesize_openai`). Should be module-level/singletons.
- **Unbounded queries / no pagination.** `monitor.get_pulse` adds a synthetic `REVIEW_OVERDUE` for *every* overdue client with no limit; `/alerts` is unbounded; `clients` list is unbounded. Chat context hard-codes `LIMIT 50`. No pagination anywhere.
- **Brittle string contracts:** synthetic IDs via `"review-overdue-" + uuid` prefix matching; brief talking points parsed by splitting on the literal `---TALKING_POINTS---`; LLM JSON parsed with a regex `\{[\s\S]*\}`. All fragile.
- **Silent failure:** `_get_structured_context()` catches *all* exceptions and returns the string "Structured data temporarily unavailable." — so DB outages look like empty answers with no alert.

**Frontend**
- **Duplication:** `const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"` is repeated in 6+ files; the `AlertRow` type is copy-pasted in `index.tsx` and `alerts.tsx`; date formatting helpers duplicated. No shared `lib/api.ts` typed client.
- **No data layer.** Every page hand-rolls `loading/error/data` with `useEffect` + `fetch`; no SWR/React Query, so no caching, dedup, retry, or revalidation; navigations refetch from scratch.
- **No types shared with backend.** Pydantic models and TS types are maintained separately by hand → drift risk.
- **Fake progress** in ingestion (timers) decoupled from reality.

**Docs / repo**
- README and dashboard reference a **seed script that doesn't exist**.
- `frontend/DESIGN_SYSTEM.md` is aspirational and partly stale (claims "no custom component CSS in globals.css" while `globals.css` defines an animation; many animations live in `tailwind.config.js`).
- No `.nvmrc`/engines, no `Dockerfile`, no CI config.

---

## 9. Code Quality Review

**Strengths**
- Readable, well-commented modules with clear single responsibilities (`llm_extractor`, `vector_store`, `cache`, `config`).
- Pydantic response models on endpoints; sensible HTTP status codes for duplicate (409) / missing table (503).
- The chat parallelism/caching is a legitimately good piece of engineering.
- Frontend components are small and mostly cohesive.

**Issues / patterns to fix**
- **Broad `except Exception`** swallowing errors (chat context, brief RAG, several places) → debug-hostile, hides outages.
- **Business logic in routers.** `monitor.py` and `chat.py` mix SQL, transformation, and LLM orchestration in endpoint functions. Extract a service/repository layer; it'll also make tests possible.
- **Magic strings** for types/statuses/priorities scattered across BE and FE; should be enums/shared constants.
- **Inconsistent label formatting** between pages (raw enums vs humanized) — symptom of no shared presentation layer.
- **TypeScript not strict end-to-end** for API payloads (responses typed as `any` via `res.json()`); no zod/io-ts validation at the boundary.
- **No tests at all.** `scripts/test_llm.py` / `test_embeddings.py` are manual smoke scripts, not a suite. There is no pytest, no React Testing Library, no Playwright e2e committed, no CI gate. For a compliance-adjacent product this is unacceptable pre-launch.
- **Logging** is a single custom stdout logger for ingestion; no structured logs, request IDs, levels, or correlation; nothing for chat/monitor.

---

## 10. Security Review

Ordered by severity. (Several overlap with §5.)

**Critical**
1. **No authentication/authorization on any endpoint** — full read of sensitive PII and full write/delete to anyone. (§5)
2. **Unauthenticated destructive endpoint** `POST /api/settings/clear-data` wipes Postgres + Qdrant.
3. **Sensitive personal & financial data with zero access control / isolation.** Per the FCA/ICO joint statement, vulnerability data (health, etc.) is **special-category** under UK GDPR and demands stricter controls — there are none. No data residency guarantee, no audit trail, no DSAR/erasure workflow, no DPIA. This is a regulatory non-starter for UK IFAs.

**High**
4. **No rate limiting / quotas** on paid LLM endpoints → financial DoS / cost-abuse.
5. **Unauthenticated, unbounded file upload.** `content = await file.read()` loads the entire file into memory with **no max size** → memory-exhaustion DoS; validation is extension-only (no MIME sniff, no AV scan).
6. **Prompt-injection / data exfiltration risk:** ingested document text is fed verbatim into chat/brief synthesis; a malicious document can carry instructions. No input sanitization or output guarding.
7. **Known-vulnerable dependency:** `next@14.2.15` is flagged by npm with a security advisory; `npm install` reports **3 vulnerabilities (1 critical)**. No Dependabot/audit gate.

**Medium**
8. **Cache cross-tenant leakage risk** once auth exists (keys not tenant-scoped).
9. **No security headers / CSP**, no HTTPS enforcement in app config, `allow_methods/headers="*"`.
10. **No secret rotation / KMS**; keys live as plain env vars (acceptable for now, but document and plan).
11. **Error messages** can leak internals (raw exception strings returned to the client in some paths).

**Positive**
- `.env` and `backend/uploads/*` are correctly gitignored; only `.env.example` (no secrets) is committed.

---

## 11. Recommended Features

Prioritized by **impact vs effort** (I = impact, E = effort, both 1–5).

### Critical before launch (table-stakes to be a SaaS at all)
- **Accounts & auth** (signup/login/SSO, password reset, email verify). *I5 E4*
- **Multi-tenant data model + RLS** (`workspace_id` everywhere; scoped Qdrant + cache). *I5 E4*
- **Roles & team members** (owner/adviser/paraplanner/admin; invites). *I4 E3*
- **Billing** (Stripe subscriptions per workspace; webhooks as source of truth; entitlements layer). *I5 E3*
- **Onboarding flow + sample data** (guided first run; empty-state-as-onboarding). *I4 E2*
- **Async ingestion + real progress** (job queue, status stream). *I3 E3*
- **Rate limiting & usage metering** (per-workspace quotas; app-layer enforcement, not just Stripe meters). *I4 E2*
- **Mobile-responsive shell** (drawer nav). *I3 E2*
- **Audit log + UK data-residency + DSAR/erasure** (compliance baseline). *I5 E4*

### High priority (drive activation, retention, trust)
- **Real conversational Ask Jarvis** with history + streaming + follow-ups. *I4 E3*
- **Close the loop on actions:** send email (or hand-off to mail client with logging), create tasks, add to calendar, write back to CRM. *I5 E4*
- **CRM/calendar integrations** (Intelliflo/Plannr/Wealthbox + Google/Microsoft calendar) — removes manual upload. *I5 E5*
- **Scheduled, genuinely proactive digests** ("your morning brief" email; pre-meeting brief auto-sent before each meeting). *I5 E3*
- **Edit/correct extracted client & alert data** (trust + data quality). *I4 E2*
- **Designed empty/loading/error states + skeletons** across all screens. *I3 E2*
- **Settings hub** (profile, firm, notifications, integrations, data/privacy, billing). *I3 E2*

### Medium priority
- **Live meeting capture / notetaker** (or integrate an existing one) to compete on the core job. *I5 E5*
- **Analytics/MI dashboard** for Consumer Duty outcomes (the four PRIN 2A outcomes) with exportable evidence packs. *I4 E3*
- **Prompt/template management** (firm-approved email & brief templates). *I3 E2*
- **Bulk operations** (multi-client briefs, batch chase emails). *I3 E2*
- **Search across all clients/documents** with filters. *I3 E2*
- **Notification center** (in-app + email + optional Slack/Teams). *I3 E2*

### Future roadmap / differentiation
- **Compliance copilot:** automated suitability/Consumer-Duty checks, immutable audit trail, "evidence in seconds." *I5 E5*
- **Memory & client timeline** (a longitudinal record per client across all interactions). *I4 E4*
- **Agent customization** (firm tone, risk language, guardrails) + **template marketplace**. *I3 E3*
- **Multi-agent workflows / automation builder** (Zapier-/n8n-style: "when review overdue 30 days → draft chase → notify"). *I4 E5*
- **Enterprise:** SSO/SAML, dedicated-DB tier, ISO 27001/SOC 2 Type II, granular RBAC, regional isolation. *I4 E5*

---

## 12. Launch Checklist

**Must-have before any paid launch**
- [ ] Authentication (signup/login/reset/verify) + protected API & routes
- [ ] Multi-tenant schema + **Postgres RLS** enforced; Qdrant payload + cache keys tenant-scoped
- [ ] Roles/permissions + team invites
- [ ] Stripe billing (plans, checkout, customer portal, webhooks, entitlements)
- [ ] Per-workspace rate limits + usage metering; remove unauthenticated cost-abuse vectors
- [ ] Remove/secure `clear-data`; add confirmation + auth + soft-delete
- [ ] File upload limits (size/type/MIME/AV) + async ingestion with real status
- [ ] Mobile-responsive navigation and layouts
- [ ] Error reporting (Sentry), structured logging, uptime/health monitoring
- [ ] Automated tests (pytest + RTL + Playwright e2e) and CI; dependency audit (fix Next.js advisory)
- [ ] Legal/compliance: ToS, Privacy Policy, DPA, cookie consent; UK data residency; DSAR/erasure; audit log; DPIA
- [ ] Secrets management & key rotation plan; security headers/CSP; HTTPS enforcement
- [ ] Backups + restore tested; data export (portability)

**Should-have**
- [ ] Onboarding + sample data; designed empty/loading/error states
- [ ] Email notifications + transactional email provider
- [ ] Settings hub; account deletion self-serve
- [ ] Landing page + pricing page + docs/help center
- [ ] Analytics (product usage) + feedback capture (e.g. in-app)
- [ ] Status page + incident process

**Nice-to-have**
- [ ] At least one CRM + calendar integration
- [ ] Conversational chat with history/streaming
- [ ] Consumer-Duty MI dashboard

---

## 13. Product Roadmap

**Phase 0 — Foundations (Weeks 1–4) — "Make it a real, single-firm app"**
Auth + multi-tenant schema + RLS; secure/secure-delete; protected API; per-page auth guards; tenant-scope caches & Qdrant filters; basic settings + profile. Outcome: a firm can have a private, isolated account.

**Phase 1 — Commercialize (Weeks 4–8) — "Make it sellable"**
Stripe billing + plans + entitlements + usage metering/rate limits; onboarding + sample data; mobile-responsive shell; Sentry + logging + CI + first test suites; landing + pricing pages; legal docs. Outcome: you can charge money safely.

**Phase 2 — Close the loop & retain (Weeks 8–14) — "Make it sticky"**
Async ingestion + real progress; conversational Ask Jarvis (history/streaming); send/log emails + tasks + calendar; scheduled proactive digests & auto pre-meeting briefs; edit/correct extracted data; first CRM + calendar integration; notification center. Outcome: it earns a daily-routine slot.

**Phase 3 — Differentiate (Weeks 14–24) — "Win the UK-compliance wedge"**
Consumer-Duty MI dashboard + evidence export; immutable audit trail; UK data-residency posture + DSAR/erasure automation; template/prompt management; analytics. Begin ISO 27001 / SOC 2 Type II path. Outcome: a defensible UK-native position.

**Phase 4 — Scale & enterprise (24 weeks+)**
Live meeting capture (build or integrate); automation/workflow builder; client memory/timeline; SSO/SAML, RBAC, dedicated-DB tier; marketplace. Outcome: move upmarket to firms.

---

## 14. Immediate Action Items

The single most important thing: **stop treating this as a demo and re-platform the foundation before adding any more features.**

1. **Lock down the running backend *today*.** At minimum, put auth (even a shared secret/API key) in front of every route and **disable or guard `clear-data`** — it currently lets anyone wipe the database. *(hours)*
2. **Add identity + tenancy as the next unit of work.** Pick Supabase Auth + RLS (fits the existing Postgres) or Clerk Organizations. Add `users`, `workspaces`, `workspace_members`, `subscriptions`, and `workspace_id` on every domain table; enforce with RLS. *(1–2 weeks)*
3. **Introduce a shared frontend API client + types** (`lib/api.ts`, shared `types.ts`) and a data layer (React Query) to kill duplication and prep for auth headers. *(days)*
4. **Move ingestion off the request path** (job queue + status) and **swap the in-memory cache for Redis** before you ever run >1 worker. *(days–1 week)*
5. **Fix the mobile shell** (drawer nav) and the cross-page label inconsistencies. *(days)*
6. **Stand up the safety net:** Sentry, structured logging, a CI pipeline, `npm audit` fix (Next.js advisory), and the first pytest + Playwright e2e tests. *(days)*
7. **Decide the wedge** (recommend: UK-compliance-native proactive layer) and write a one-page positioning doc so feature priorities align to it.

---

## 15. Screenshots

Captured with Playwright (Chromium) against the running app. Desktop = 1440×900, mobile = 390×844. Files are in [`review-screenshots/`](review-screenshots/).

| Screen | Desktop | Mobile | Notes |
|--------|---------|--------|-------|
| Dashboard | `dashboard-desktop.png` | `dashboard-mobile.png` | Mobile crushed by fixed sidebar (critical). |
| Ask Jarvis | `chat-desktop.png` | `chat-mobile.png` | + `chat-answer-desktop.png` (answer + sources). |
| Pre-meeting brief | `brief-desktop.png` | `brief-mobile.png` | + `brief-generated-desktop.png` (brief + talking points). |
| Ingestion | `ingestion-desktop.png` | `ingestion-mobile.png` | Fake progress steps. |
| Alerts | `alerts-desktop.png` | `alerts-mobile.png` | Raw enum labels (`FOLLOW_UP`, `REVIEW_OVERDUE`). |
| Settings | `settings-desktop.png` | `settings-mobile.png` | Near-empty; copy says "demo". |
| Draft email modal | `draft-email-modal-desktop.png` | — | Works; lacks focus trap. |
| Clear-data confirm | `settings-confirm-desktop.png` | — | Text-only confirm on a destructive, unauth'd action. |

> Note: screenshots were captured against a small **mock backend** (`.audit/mock_server.py`) seeded with realistic UK-IFA sample data, because no live Supabase/Qdrant/OpenAI credentials were available. The mock is throwaway and not part of the product; populated screens are representative of real layouts. Empty/error states differ when no backend is connected (the dashboard shows "No priorities yet" and an amber API-error banner).

---

## 16. Final Recommendations

1. **Reframe the project.** This is an excellent *prototype of a retrieval architecture and a clean desktop UI*, not a product. The work ahead is ~80% platform (auth, tenancy, billing, compliance, ops) and ~20% feature polish. Plan accordingly.
2. **Do not add features until the foundation exists.** Every feature built on a single-tenant, unauthenticated base is throwaway. Auth + tenancy + RLS is the gate.
3. **Make it actually proactive.** Today the "agent" is a read-time list plus a manual time slider. The product only becomes valuable when it *acts on a schedule* (morning digest, auto pre-meeting brief, overdue chase) and *closes the loop* (send/log/task/CRM write-back). That is the difference between "a clever demo" and "a tool I open every morning."
4. **Pick the UK-compliance wedge and own it.** Don't fight Jump on meeting capture; integrate with it. Win on Consumer-Duty MI, FCA/ICO-aware data handling, UK residency, and Intelliflo/Plannr integration — the soft underbelly of US incumbents.
5. **Treat security & compliance as features, not chores.** For sensitive UK client data, RLS, audit trails, data residency, and DSAR/erasure are *prerequisites* and also *sales arguments*. Start the SOC 2 / ISO 27001 conversation early.
6. **Invest disproportionately in onboarding and the empty state** — research is unanimous that this is the highest-leverage surface for activation and retention, and it is currently the weakest.
7. **Keep what's good.** The hybrid RAG + structured-context design, the caching/parallelism, the duplicate detection, and the desktop design system are real foundations worth carrying forward.

*This report is intended to serve as the implementation roadmap for the coming weeks. Start with §14, item 1 — within the hour.*
