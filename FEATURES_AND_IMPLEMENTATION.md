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
- **Path B – Chunk → embed → Qdrant:** Text chunked, embedded, upserted to `proactive_jarvis_agent_client_memory`.
- **Document ↔ client linking** — Each upload is linked to the client it produced (`ingested_documents.client_id`, migration 002) and counted on Client 360.
- **Transcript ingestion** — Paste a meeting transcript and run the same dual-path pipeline as uploads (`POST /api/ingest/transcript`), with content-hash dedup.
- **Async ingestion + job status** — Durable Postgres job queue (`services/jobs.py`), drained event-driven right after each enqueue (worker Lambda in AWS via `services/worker_trigger.py`, in-process background task locally — no polling loop): `POST /api/ingest/upload-async` returns a job id, polled at `GET /api/ingest/jobs/{id}`. The synchronous `/upload` is unchanged.
- **Note templates** — Structured meeting-note skeletons (discovery, annual review, prospect, suitability) via `GET /api/ingest/note-templates` (`services/note_templates.py`), with copy-to-clipboard.
- **Compliance signal scan** — Paste notes to flag vulnerability drivers (FCA FG21/1) and Consumer Duty signals; deterministic word-boundary matching with contextual excerpts (`POST /api/compliance/scan`, `services/compliance.py`).
- **AI audit log** — In-memory, accountable trail of AI outputs (review notes, draft emails, digests) via `GET /api/compliance/audit` (`services/audit.py`), shown on Settings and cleared on data reset.
- **Human-review approval gate** — Mark AI outputs as reviewed (`POST /api/compliance/audit/{id}/approve`) — a Consumer-Duty accountability step surfaced on the Settings audit log.
- **Data-handling & AI posture** — `GET /api/compliance/posture` reports configured residency, retention, LLM provider, encryption and that the app never trains on client data (`services/posture.py`); shown on Settings.
- **Extraction cache** — LLM result cached by content hash (24 h).
- **Upload validation** — Magic-byte checks and size limits via `safety.py`; the deployment's limit and allowed types are exposed at `GET /api/ingest/limits`, so the UI shows the real number (20 MB locally, 4 MB on Lambda) before upload and validates client-side.
- **Structured errors** — Every API error carries `{"error": {"code", "message", "retryable"}}` alongside the legacy `detail` (handlers in `app/main.py`). Messages are fixed, friendly copy — provider/SQL/stack detail stays in server logs (`safety.public_error_message`). LLM outages surface as `503 ai_unavailable`, vector-search outages as `503` "Search is temporarily unavailable" — document data stays accessible either way.

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

## 9. Multi-agent runtime, model gateway, and evals

### What we implemented

- **Quota-aware free-tier model gateway** — every completion routes through `services/model_gateway.py`: an ordered candidate chain per purpose (chat, brief, draft, extraction, agent, reviewer, fast) across Groq, Cerebras, Gemini, Moonshot, and OpenRouter free tiers, with DeepSeek/OpenAI as optional paid plug-ins. Per-provider/per-model RPM+RPD counters live in Postgres (`bump_llm_quota()`, SECURITY DEFINER; in-process fallback), so published free-tier caps are enforced *before* a request is sent; 429/5xx/auth failures apply cooldowns and fall down the chain. Model pins (`LLM_MODEL` etc.) and route overrides (`LLM_ROUTE_<PURPOSE>`) are env-configurable.
- **LangGraph agent runtime** — copilot questions and briefs run as durable **agent runs** on the existing Postgres job queue (job kind `agent_run`, worker Lambda, 900 s budget): plan → gather (RLS-scoped tools) → synthesize → **cross-model compliance review** → finalize, with one revision loop on review failure and hard step/revision budgets in the runtime. A planner LLM picks 1–3 read-only tools (semantic search, structured records, book analytics, client scores, upcoming alerts — `services/agent_tools.py`); briefs use a deterministic plan. The reviewer always runs on a *different model family* than the generator and combines an LLM critique with deterministic citation checks (phantom `[n]` refs fail closed).
- **Real step timeline + replay** — every node and tool call is recorded in `agent_runs`/`agent_steps` (org-scoped RLS, migration 0013). The frontend polls the run (ingest-style backoff) and renders the live timeline (`AgentTimeline`), replacing the simulated thinking card; `/runs/[id]` is the full replay/audit view (steps, models used, review verdict, output). Copilot answers show a "Reviewed" badge and a "View reasoning" link.
- **Local embeddings (no API)** — `services/embeddings.py` defaults to fastembed `bge-small-en-v1.5` (384-dim ONNX on CPU, baked into the Docker image): the query path can never hit a provider quota and document text never leaves the backend. Legacy OpenAI embeddings remain via `EMBEDDINGS_PROVIDER=openai`; `scripts/reindex_embeddings.py` migrates existing documents; collections are auto-created per provider (`vector_store.ensure_collection`).
- **Observability + evals** — optional Langfuse tracing (`services/tracing.py`, env-gated, fail-open): every gateway call is a generation event, every agent run a trace with per-step spans, with a content-masking mode for real data. A **50-case golden eval set** (`backend/evals/`) grades grounding, citation accuracy, hallucination (numeric grounding), missing-data honesty, prompt-injection resistance, the regulated-advice boundary, and extraction quality — deterministic graders gate (critical injection/advice cases fail the build), an LLM judge is optional, and CI runs it on prompt/gateway/agent changes when provider secrets exist.

### How we achieved it

- **Backend:** `POST /api/agent/runs`, `GET /api/agent/runs/{id}` — `backend/app/routers/agent.py`; graph in `backend/app/agents/graph.py`; gateway in `backend/app/services/model_gateway.py`; persistence in `backend/app/services/agent_runs.py`; tools in `backend/app/services/agent_tools.py`; migrations `0012`–`0013`.
- **Frontend:** `frontend/lib/agent.ts`, `frontend/components/ai/AgentTimeline.tsx`, `frontend/pages/runs/[id].tsx`; the copilot page (`chat.tsx`) creates and polls runs via `useAgentChat`, falling back to the synchronous `/api/chat` on older backends.
- **Credits:** one reservation spans the whole run (reserve at POST, commit/release in the worker) — retries never double-charge.

---

## 10. Technical summary

| Area | Implementation |
|------|----------------|
| **Cache TTLs** | Brief 1 h, draft 30 min, chat 5 min, digest 60 s, structured context 90 s, extraction 24 h |
| **Database** | PostgreSQL (Supabase): `clients`, `alerts`, `ingested_documents`, `agent_runs`, `agent_steps`, `llm_quota_counters`; connection pooling in `db.py` |
| **Vector store** | Qdrant `proactive_jarvis_agent_client_memory`, 384 dims, COSINE (fastembed default); legacy `client_memory` 1536 dims with `EMBEDDINGS_PROVIDER=openai` |
| **LLM** | Multi-provider gateway: free tiers first (Groq/Cerebras/Gemini/Moonshot/OpenRouter), DeepSeek/OpenAI optional; per-purpose routes, quota tracking, fallbacks |
| **Agents** | LangGraph plan→gather→synthesize→review→finalize; durable runs on the job queue; cross-model review; step timeline + replay |
| **Security** | Input clamping, RAG injection stripping, rate limits, safe redirects — `safety.py`; agent tools are read-only and RLS-scoped |
| **Observability** | Langfuse tracing (optional), structured `llm_usage`/`llm_call` events, 50-case eval harness in CI |
| **Frontend** | React Query hooks, lazy-loaded modals, Playwright E2E with POM |
| **Tests** | Backend unit tests via `pytest` (run `pip install -r requirements-dev.txt`, then `pytest`); frontend Playwright E2E against a mock server |

For setup and running locally, see the main [README](README.md#run-the-project-locally).
