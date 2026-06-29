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
- **Conversation memory** — Multi-turn threads via an in-memory conversation store; `conversation_id` flows through requests so follow-ups are context-aware (`services/conversations.py`).

### How we achieved it

- **Backend:** `POST /api/chat` — `backend/app/routers/chat.py`, `backend/app/services/rag_context.py`, `backend/app/services/prompts.py`, `backend/app/services/llm.py`, `backend/app/services/conversations.py`.
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

- **Client list** — Table with last review, assets, risk score, open alert count, plus a book-analytics strip (clients, AUM, average risk, reviews overdue).
- **Client detail** — Profile snapshot (incl. linked document count), open alerts, links to brief and Copilot.
- **Edit details** — Correct mis-extracted profile fields (name, assets, cash, risk, retirement age, last review) via a modal, validated server-side.
- **Client intelligence** — Deterministic engagement-risk and profile-completeness scores plus a ranked next-best-action list, computed from existing data (no LLM).
- **Review note** — One-click Consumer-Duty review note (LLM with a deterministic fallback so it works without an LLM), with copy-to-clipboard.
- **Playbooks** — Apply a task template (annual review, onboarding, protection review) to a client to create a standard set of alerts.

### How we achieved it

- **Backend:** `GET /api/monitor/clients`, `GET /api/monitor/clients/{id}`, `PATCH /api/monitor/clients/{id}`, `GET /api/monitor/analytics`, `POST /api/monitor/clients/{id}/review-note`, `GET /api/monitor/playbooks`, `POST /api/monitor/clients/{id}/apply-playbook` — `monitor.py`; validation in `services/client_updates.py`; pure scoring in `services/scores.py`; aggregation in `services/analytics.py`; review-note fallback in `services/review_note.py`; playbook catalog in `services/playbooks.py`.
- **Frontend:** `frontend/pages/clients/index.tsx`, `frontend/pages/clients/[id].tsx`, `frontend/components/EditClientModal.tsx`, `frontend/components/ReviewNoteModal.tsx`.

---

## 5. Document ingestion (dual-path)

### What we implemented

- **Upload PDF and DOCX** — Fact-finds, meeting notes.
- **Duplicate detection** — By content hash (SHA-256).
- **Path A – LLM extraction → Postgres:** Client profile and alerts (`DEADLINE`, `OPPORTUNITY`, `COMPLIANCE`, `FOLLOW_UP`).
- **Path B – Chunk → embed → Qdrant:** Text chunked, embedded, upserted to `client_memory`.
- **Document ↔ client linking** — Each upload is linked to the client it produced (`ingested_documents.client_id`, migration 002) and counted on Client 360.
- **Transcript ingestion** — Paste a meeting transcript and run the same dual-path pipeline as uploads (`POST /api/ingest/transcript`), with content-hash dedup.
- **Async ingestion + job status** — Background processing via FastAPI BackgroundTasks (in-process, no external worker): `POST /api/ingest/upload-async` returns a job id, polled at `GET /api/ingest/jobs/{id}` (`services/jobs.py`). The synchronous `/upload` is unchanged.
- **Note templates** — Structured meeting-note skeletons (discovery, annual review, prospect, suitability) via `GET /api/ingest/note-templates` (`services/note_templates.py`), with copy-to-clipboard.
- **Compliance signal scan** — Paste notes to flag vulnerability drivers (FCA FG21/1) and Consumer Duty signals; deterministic word-boundary matching with contextual excerpts (`POST /api/compliance/scan`, `services/compliance.py`).
- **AI audit log** — In-memory, accountable trail of AI outputs (review notes, draft emails, digests) via `GET /api/compliance/audit` (`services/audit.py`), shown on Settings and cleared on data reset.
- **Human-review approval gate** — Mark AI outputs as reviewed (`POST /api/compliance/audit/{id}/approve`) — a Consumer-Duty accountability step surfaced on the Settings audit log.
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

## 7. Settings, data export, onboarding, and clear data

### What we implemented

- **Data export (CSV)** — Download the client book or alert list as a CSV (RFC 4180 quoting).
- **Load demo data** — One-click seeding of a realistic demo book from the dashboard first-run (only when the workspace is empty).
- **Clear data** — Removes clients, alerts, documents, Qdrant vectors, and in-memory caches.

### How we achieved it

- **Backend:** `GET /api/monitor/export` (serializer in `services/export.py`); `POST /api/settings/load-sample-data` (dataset in `services/sample_data.py`); `POST /api/settings/clear-data` — `backend/app/routers/settings.py`.
- **Frontend:** `frontend/pages/settings.tsx`, `frontend/lib/export.ts`, dashboard first-run in `frontend/pages/dashboard.tsx`.

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
| **Tests** | Backend unit tests via `pytest` (run `pip install -r requirements-dev.txt`, then `pytest`); frontend Playwright E2E against a mock server |

For setup and running locally, see the main [README](README.md#run-the-project-locally).
