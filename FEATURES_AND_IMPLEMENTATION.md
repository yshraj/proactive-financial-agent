# Features & Implementation

This document describes **all features** implemented in **KritiFin** (Proactive Financial Agent) and **how each was achieved**. For a high-level overview, see the [Solution overview](README.md#solution-overview) in the main README.

---

## 1. Dashboard (Pulse, briefing & time-travel)

### What we implemented

- **Time-travel date picker** — Choose a simulated "today" to see what would be due on that date.
- **Morning AI briefing** — LLM-generated digest of open priorities and suggested focus (`DigestCard`).
- **Demo spotlight** — Top-priority client card with Prepare brief, Ask Copilot, and Draft email actions.
- **Priority timeline** — Ranked alerts for the next 30 days with inline actions.
- **Review overdue** — Synthetic `REVIEW_OVERDUE` alerts for clients without a review in 12+ months.
- **Overdue follow-ups** — PENDING `FOLLOW_UP` alerts before the simulated date.
- **Pulse KPIs** — Reviews due, follow-ups, high priority, compliance items, documents processed.
- **Draft email** — LLM-generated email draft per alert; cached 30 min by `alert_id`.
- **Mark done** — Update alert status to `COMPLETED`.
- **Recently completed** — Completed alerts (collapsible section).

### How we achieved it

- **Backend:** `GET /api/monitor/pulse`, `GET /api/monitor/digest`, `POST /api/monitor/draft-email`, `PATCH /api/monitor/alerts/{id}/status` — `backend/app/routers/monitor.py`, `backend/app/services/alert_helpers.py`.
- **Frontend:** `frontend/pages/dashboard.tsx`, `frontend/components/DigestCard.tsx`, `frontend/components/DemoSpotlight.tsx`, `frontend/lib/demo.ts`.

---

## 2. AI Copilot (hybrid RAG + structured data)

### What we implemented

- **Hybrid context** — Structured Postgres data plus semantic Qdrant search over ingested documents.
- **Client scope** — Book-wide or single-client queries via `ClientSelect` and `?clientId=` deep link.
- **Auto-ask deep link** — `?q=` query parameter triggers Copilot on page load.
- **Citation UX** — Markdown answers, source list, trust footer, thinking states, follow-up chips.
- **Caching** — Response cache (5 min); structured context cache (90 s); parallel DB + embedding on miss.

### How we achieved it

- **Backend:** `POST /api/chat` — `backend/app/routers/chat.py`, `backend/app/services/rag_context.py`, `backend/app/services/prompts.py`, `backend/app/services/llm.py`.
- **Frontend:** `frontend/pages/chat.tsx`, `frontend/components/ai/`, `frontend/lib/ai.ts`.

---

## 3. Pre-meeting brief

### What we implemented

- **Client selector** — Dropdown with deep-link auto-select (`?clientId=&auto=1`).
- **One-page brief** — Key facts, upcoming items, commitments with source citations.
- **Suggested talking points** — Parsed after `---TALKING_POINTS---` delimiter.
- **Regenerate** — Refresh brief on demand.
- **Caching** — Brief cached by `client_id` (1 hour).

### How we achieved it

- **Backend:** `POST /api/chat/brief` — RAG via `retrieve_for_brief()` in `rag_context.py`.
- **Frontend:** `frontend/pages/brief.tsx`, `frontend/components/ClientSelect.tsx`.

---

## 4. Client 360

### What we implemented

- **Client list** — Table with last review, assets, risk score, open alert count.
- **Client detail** — Profile snapshot, open alerts, ingested documents, links to brief and Copilot.

### How we achieved it

- **Backend:** `GET /api/monitor/clients`, `GET /api/monitor/clients/{id}` — `monitor.py`.
- **Frontend:** `frontend/pages/clients/index.tsx`, `frontend/pages/clients/[id].tsx`.

---

## 5. Document ingestion (dual-path)

### What we implemented

- **Upload PDF and DOCX** — Fact-finds, meeting notes.
- **Duplicate detection** — By content hash (SHA-256).
- **Path A – LLM extraction → Postgres:** Client profile and alerts (`DEADLINE`, `OPPORTUNITY`, `COMPLIANCE`, `FOLLOW_UP`).
- **Path B – Chunk → embed → Qdrant:** Text chunked, embedded, upserted to `client_memory`.
- **Extraction cache** — LLM result cached by content hash (24 h).
- **Upload validation** — Magic-byte checks and size limits via `safety.py`.

### How we achieved it

- **Backend:** `POST /api/ingest/upload` — `backend/app/routers/ingest.py`, `backend/app/services/llm_extractor.py`, `backend/app/services/prompts.py`.
- **Frontend:** `frontend/pages/admin.tsx`, `frontend/lib/ingest.ts`.

---

## 6. Alerts list and filters

### What we implemented

- **Alerts page** — Filters: simulated date, window, type, priority, status.
- **Consistent with Pulse** — Same date logic and synthetic `REVIEW_OVERDUE` handling.

### How we achieved it

- **Backend:** `GET /api/monitor/alerts` — `monitor.py`.
- **Frontend:** `frontend/pages/alerts.tsx`.

---

## 7. Settings and clear data

### What we implemented

- **Clear data** — Removes clients, alerts, documents, Qdrant vectors, and in-memory caches.

### How we achieved it

- **Backend:** `POST /api/settings/clear-data` — `backend/app/routers/settings.py`.
- **Frontend:** `frontend/pages/settings.tsx`.

---

## 8. Authentication

### What we implemented

- **Supabase Auth** — Login and signup pages with JWT forwarded to the API.
- **Graceful degradation** — When Supabase is unconfigured, **Enter demo workspace** bypasses auth.

### How we achieved it

- **Backend:** JWT verification in `backend/app/security.py` (ES256 via JWKS, HS256 fallback).
- **Frontend:** `frontend/pages/login.tsx`, `frontend/pages/signup.tsx`, `frontend/lib/supabase/client.ts`.

---

## 9. Technical summary

| Area | Implementation |
|------|----------------|
| **Cache TTLs** | Brief 1 h, draft 30 min, chat 5 min, digest 60 s, structured context 90 s, extraction 24 h |
| **Database** | PostgreSQL (Supabase): `clients`, `alerts`, `ingested_documents`; connection pooling in `db.py` |
| **Vector store** | Qdrant `client_memory`, 1536 dims, COSINE distance |
| **LLM** | OpenAI GPT-4o (or Gemini); briefs use `BRIEF_LLM_MODEL` (default gpt-4o-mini) |
| **Security** | Input clamping, RAG injection stripping, rate limits, safe redirects — `safety.py` |
| **Frontend** | React Query hooks, lazy-loaded modals, Playwright E2E with POM |

For setup and running locally, see the main [README](README.md#run-the-project-locally).
