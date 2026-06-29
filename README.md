# KritiFin (Proactive Financial Agent)

**KritiFin** is a proactive AI workspace for UK financial advisers: a morning dashboard of priorities, AI Copilot over your client book and ingested documents, pre-meeting briefs with citations, overdue follow-ups, and draft emails — so advisers spend less time reactive and more time adding value.

**Live demo:** The frontend deploys on [Vercel](https://vercel.com) and the backend on [Render](https://render.com). If the backend is slow to respond, Render may be spinning up after inactivity.

**Presenter guide:** See [docs/live-demo-script.md](docs/live-demo-script.md) for a 5–10 minute walkthrough.

---

## Submission checklist

| Requirement | Covered |
|-------------|---------|
| Clear repository name | `proactive-financial-agent` |
| Clean folder structure | [Repository layout](#repository-layout) — `backend/`, `frontend/`, `docs/` |
| No compiled binaries or credentials | `.gitignore` excludes `.env`, `node_modules/`, `.next/`, uploads, Playwright artifacts |
| **README.md** | Project name, problem, solution, stack, setup, env vars, run locally |
| **LICENSE** | MIT — see [LICENSE](LICENSE) |
| **Documentation** | [docs/README.md](docs/README.md) index |

**Current setup:** Supabase (PostgreSQL + optional auth), Qdrant Cloud (vectors), OpenAI (LLM + embeddings). Copy [`.env.example`](.env.example) to `.env` and fill in keys.

---

## Chosen problem

UK Independent Financial Advisers (IFAs) typically manage 150–250 clients under FCA and Consumer Duty rules. They want to be proactive but end up reactive: emails, calls, and admin consume 60–70% of the day. Critical details sit in CRM notes and meeting transcripts and are hard to surface at the right moment.

This project tackles:

- **Reactive trap** — One place to see what's due and what to do first.
- **Memory problem** — Natural-language questions over client data and ingested documents.
- **Information overload** — Documents extracted, structured, and indexed for dashboard and AI.
- **Compliance burden** — Review-overdue (12+ months) and follow-ups visible with rationale.
- **Follow-up commitments** — "Waiting on client" items extracted and surfaced as overdue follow-ups.

---

## Solution overview

| Feature | Description |
|---------|-------------|
| **Dashboard** | Time-travel date picker, morning AI briefing, priority timeline, spotlight card, KPIs, draft email, mark done |
| **AI Copilot** | Hybrid RAG + structured data; book-wide or client-scoped queries; citation-linked answers |
| **Meeting brief** | One-page brief with talking points and source documents; auto-generate via deep link |
| **Client 360** | Client list and detail pages — profile, alerts, documents, AI actions |
| **Ingestion** | Upload PDF/DOCX; LLM extracts clients and alerts; text indexed in Qdrant for RAG |
| **Alerts** | Filterable alert list consistent with dashboard Pulse logic |
| **Auth** | Supabase sign-in with graceful degradation when unconfigured (demo mode) |

Mock data only (no live CRM). Schema and prompts are tuned for UK fact-find style.

**Detailed implementation:** [FEATURES_AND_IMPLEMENTATION.md](FEATURES_AND_IMPLEMENTATION.md)

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS, TanStack Query |
| Backend | FastAPI (Python 3.12), Uvicorn |
| Structured data | PostgreSQL (Supabase) — clients, alerts, ingested_documents |
| Vector search | Qdrant — semantic index for RAG |
| LLM | OpenAI GPT-4o (or Gemini via `LLM_PROVIDER`) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Auth | Supabase Auth (optional) |
| E2E tests | Playwright with Page Object Model |

---

## Environment variables

All backend variables are in [`.env.example`](.env.example) at the **project root**. Copy to `.env` — **never commit `.env`**.

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string |
| `QDRANT_URL` | Yes | Qdrant cluster URL |
| `QDRANT_API_KEY` | Yes (Cloud) | Qdrant API key |
| `OPENAI_API_KEY` | Yes (OpenAI) | LLM and embeddings |
| `SUPABASE_URL` | No | Enables JWT verification on API |
| `SUPABASE_JWT_SECRET` | No | Legacy HS256 token verification |
| `API_KEY` | No | API key gate for production |
| `LLM_PROVIDER` | No | `openai` (default) or `gemini` |
| `CORS_ORIGINS` | No | Default `http://localhost:3000` |

**Frontend** (`frontend/.env.local`, optional):

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | — | Supabase project URL (auth) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — | Supabase anon key (auth) |

See [Setting up Supabase](#setting-up-supabase-database) and [Setting up Qdrant](#setting-up-qdrant-vector-store) below.

---

## Setting up Supabase (database)

1. Create a project at [supabase.com](https://supabase.com).
2. **Connection string:** Project Settings → Database → URI → Connection pooling (Transaction mode). Set as `DATABASE_URL`.
3. **Schema:** SQL Editor → run `backend/supabase_schema.sql`.
4. **Auth (optional):** Project Settings → API → copy URL and anon key to `frontend/.env.local`.

---

## Setting up Qdrant (vector store)

**Qdrant Cloud (recommended)**

1. Create a cluster at [cloud.qdrant.io](https://cloud.qdrant.io).
2. Set `QDRANT_URL` and `QDRANT_API_KEY` in `.env`.
3. Create the collection:
   ```bash
   cd backend && python scripts/create_qdrant_collection.py
   ```

**Local (Docker):** `docker run -p 6333:6333 qdrant/qdrant` — set `QDRANT_URL=http://localhost:6333`, leave API key empty, then run the script above.

---

## Setup instructions

### Prerequisites

- Python 3.10+ (3.12 recommended)
- Node.js 18+ and npm
- Supabase, Qdrant, and OpenAI (or Gemini) accounts

### 1. Clone and install backend

```bash
git clone <your-repo-url>
cd proactive-financial-agent

cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Database and vector store

Complete Supabase and Qdrant setup above.

### 3. Environment file

From the **project root**:

```bash
cp .env.example .env
# Edit .env with your keys
```

Optional frontend config:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > frontend/.env.local
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for Vercel + Render production config.

### 4. Frontend

```bash
cd frontend
npm install
```

---

## Run the project locally

### Step 1 — Backend

```bash
cd backend
source .venv/bin/activate   # if not already active
uvicorn app.main:app --reload --port 8000
```

Confirm: [http://localhost:8000/health](http://localhost:8000/health) → `{"status":"ok"}`

### Step 2 — Frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). If auth is not configured, use **Enter demo workspace** on the login page.

### Step 3 — Use the app

1. **Ingestion** — Upload PDF or Word fact-finds / meeting notes.
2. **Dashboard** — Morning briefing, priority timeline, draft emails.
3. **Meeting Brief** — Select a client or use Prepare brief from dashboard.
4. **AI Copilot** — Ask book-wide or client-scoped questions.
5. **Clients** — Browse client 360 views.
6. **Settings** — Clear all data to reset the workspace.

### Step 4 — Run tests (optional)

```bash
cd frontend
npm run test:e2e          # starts mock API + dev server automatically
```

See [frontend/tests/README.md](frontend/tests/README.md) for CI and deployed-environment runs.

---

## Repository layout

```
proactive-financial-agent/
├── README.md
├── LICENSE
├── .env.example
├── FEATURES_AND_IMPLEMENTATION.md
├── DEPLOYMENT.md
├── docs/                      # Guides, demo script, planning archive
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/           # ingest, monitor, chat, settings
│   │   └── services/          # llm, prompts, rag_context, safety, cache, …
│   ├── scripts/
│   ├── tests/
│   ├── uploads/               # gitignored; .gitkeep committed
│   └── supabase_schema.sql
└── frontend/
    ├── pages/                 # dashboard, chat, brief, clients, admin, …
    ├── components/            # UI library, AI components, layout
    ├── hooks/                 # React Query API hooks
    ├── lib/                   # API client, types, routes, demo helpers
    └── tests/                 # Playwright E2E suite
```

No credentials or build artifacts are committed. Playwright reports and `.next/` are gitignored.

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/live-demo-script.md](docs/live-demo-script.md) | Live demo walkthrough |
| [FEATURES_AND_IMPLEMENTATION.md](FEATURES_AND_IMPLEMENTATION.md) | Feature deep-dive |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Production deployment |
| [docs/planning/](docs/planning/) | Roadmap and release notes |

---

## Contributing

1. Fork and clone the repository.
2. Follow setup above; use `frontend/.env.test` for E2E defaults.
3. Run `npm run lint`, `npm run typecheck`, and `npm run build` in `frontend/` before opening a PR.
4. Keep commits focused — see [docs/planning/IMPLEMENTATION_PLAN.md](docs/planning/IMPLEMENTATION_PLAN.md) for milestone context.
