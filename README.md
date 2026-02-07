# Proactive Financial Agent (Jarvis)

A proactive assistant for UK financial advisers: dashboard of priorities, Ask Jarvis (hybrid RAG + structured data), pre-meeting briefs with suggested talking points, overdue follow-ups, and draft emails—so advisers spend less time reactive and more time adding value.

---

### Submission checklist

| Requirement | Covered |
|-------------|---------|
| Clear repository name | proactive-financial-agent |
| Clean folder structure | [Repository Layout](#repository-layout) below: `backend/`, `frontend/`, no clutter. |
| No compiled binaries or credentials | `.gitignore` excludes `.env`, `__pycache__/`, `node_modules/`, `.next/`, `backend/uploads/*`. Only `.env.example` (no secrets) is committed. |
| **README.md** | |
| → Project name | **Proactive Financial Agent (Jarvis)** (title above). |
| → Chosen problem | [Chosen Problem](#chosen-problem). |
| → Solution overview | [Solution Overview](#solution-overview). |
| → Tech stack used | [Tech Stack](#tech-stack). |
| → Setup instructions | [Setting up Supabase](#setting-up-supabase-database), [Setting up Qdrant](#setting-up-qdrant-vector-store), [Setup Instructions](#setup-instructions). |
| → Environment variables | [Environment Variables](#environment-variables) and [`.env.example`](.env.example). |
| → Step-by-step run locally | [Run the Project Locally](#run-the-project-locally). |

**Current setup (as used in this project):** Supabase for PostgreSQL, Qdrant Cloud for the vector store, OpenAI for LLM and embeddings. See `.env.example` for the exact variables; copy to `.env` and fill in your keys.

---

## Chosen Problem

UK Independent Financial Advisers (IFAs) typically manage 150–250 clients under FCA and Consumer Duty rules. They want to be proactive but end up reactive: emails, calls, and admin consume 60–70% of the day. Critical details (life events, concerns, follow-up commitments) sit in CRM notes and meeting transcripts and are hard to surface at the right moment. The brief asks for a **proactive agent** that acts at the **right moment**, in the **right context**, with the **right intent**—not just a chatbot.

This project tackles:

- **Reactive trap** – One place to see what’s due and what to do first.
- **Memory problem** – Natural-language questions over client data and ingested documents (fact-finds, meeting notes).
- **Information overload** – Documents are extracted, structured, and indexed so insights surface on the dashboard and in chat.
- **Compliance burden** – Review-overdue (12+ months) and follow-ups visible; recommendations and rationale searchable in documents.
- **Follow-up commitments** – “Waiting on client” items extracted from documents and shown as overdue follow-ups on the dashboard.

---

## Solution Overview

- **Dashboard** – Time-travel date picker; “Start here” priorities (next 30 days); review overdue; **overdue follow-ups** (waiting on client); Pulse alerts (DEADLINE, OPPORTUNITY, COMPLIANCE, FOLLOW_UP); draft email and mark done; KPIs and recent completed alerts.
- **Ask Jarvis** – Hybrid chat: structured data (client list, review overdue, upcoming alerts, overdue follow-ups) plus semantic search over ingested documents. Suggestion chips for investments, compliance, business, and follow-up questions. **Caching:** responses cached by query hash (5 min); structured context cached (90 s) so DB isn’t hit on every query; on cache miss, DB and embedding run in parallel for lower latency.
- **Pre-meeting brief** – Pick a client; one-page brief (facts, upcoming items, commitments from docs) plus **suggested talking points**.
- **Ingestion** – Upload PDF/DOCX (fact-finds, meeting notes); LLM extracts client profile and alerts (review dates, DOBs, policy end dates, **follow-ups / waiting on client**); same text is chunked and indexed in Qdrant for RAG. Duplicate detection by content hash.

Mock data only (no live CRM/Intelliflo). Schema and prompts are tuned for UK fact-find style (e.g. “Last Updated”, “Next Review”, “RECOMMENDATIONS STATUS”, “UPCOMING ACTIONS”).

**For a detailed list of all features and how they were implemented, see [Features & Implementation](FEATURES_AND_IMPLEMENTATION.md).**

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14 (React), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.12), Uvicorn |
| Structured data | PostgreSQL (Supabase) – clients, alerts, ingested_documents |
| Vector search | Qdrant – semantic index for RAG |
| LLM | OpenAI GPT-4o (or Gemini via `LLM_PROVIDER`) – extraction and chat synthesis |
| Embeddings | OpenAI text-embedding-3-small (1536 dims) for Qdrant |

---

## Environment Variables

All variables are listed in `.env.example` with short comments. Copy it to `.env` at the **project root** and fill in values. **Do not commit `.env`.**

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `DATABASE_URL` | Yes | [Setting up Supabase](#setting-up-supabase-database) below |
| `QDRANT_URL` | Yes | [Setting up Qdrant](#setting-up-qdrant-vector-store) below |
| `QDRANT_API_KEY` | Yes for Qdrant Cloud | [Setting up Qdrant](#setting-up-qdrant-vector-store) below |
| `OPENAI_API_KEY` | Yes (if using OpenAI) | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `LLM_PROVIDER` | No | `openai` (default) or `gemini` |
| `LLM_MODEL` | No | e.g. `gpt-4o` (default) |
| `BRIEF_LLM_MODEL` | No | Lighter model for briefs; default `gpt-4o-mini` |
| `EMBEDDING_PROVIDER` | No | `openai` (default), `cohere`, or `gemini` |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` (default; 1536 dims for Qdrant) |
| `CORS_ORIGINS` | No | Default `http://localhost:3000` |
| `QDRANT_COLLECTION` | No | Default `client_memory` |
| `ADVISER_ID` | No | Optional UUID for ingested clients |

If you use **Gemini** for LLM or embeddings, set `GEMINI_API_KEY` or `GOOGLE_API_KEY` and the corresponding provider.

---

## Setting up Supabase (Database)

1. **Create an account and project** at [supabase.com](https://supabase.com). Create a new project (choose region, set a database password and store it safely).
2. **Get the connection string**
   - In the dashboard: **Project Settings** (gear) → **Database**.
   - Under **Connection string**, select **URI**.
   - Choose **Connection pooling** (Transaction mode) and copy the URI. It looks like:
     `postgresql://postgres.PROJECT_REF:YOUR-PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres`
   - Replace `[YOUR-PASSWORD]` with the database password you set when creating the project. Use this as `DATABASE_URL` in `.env`.
3. **Create the schema**
   - In the dashboard: **SQL Editor** → **New query**.
   - Paste and run the contents of `backend/supabase_schema.sql` (creates `clients`, `alerts`, `ingested_documents`, indexes, triggers).
   - If the migrations table is used, also run `backend/migrations/001_ingested_documents.sql` if needed (the main schema file may already include that table).

---

## Setting up Qdrant (Vector store)

**Option A – Qdrant Cloud (recommended for quick setup)**

1. **Create an account** at [cloud.qdrant.io](https://cloud.qdrant.io).
2. **Create a cluster** (e.g. free tier): choose region and create. Wait until it is running.
3. **Get URL and API key**
   - Open your cluster → **Overview** or **Details**. Copy the **Cluster URL** (e.g. `https://xxxxx.aws.cloud.qdrant.io`). Set as `QDRANT_URL` in `.env`.
   - Go to **API Keys** → create a key. Set it as `QDRANT_API_KEY` in `.env`.
4. **Create the collection** (one-off, after `.env` is set):
   ```bash
   cd backend
   python scripts/create_qdrant_collection.py
   ```
   This creates the `client_memory` collection with 1536-dimensional vectors (OpenAI `text-embedding-3-small`).

**Option B – Local Qdrant (Docker)**

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Set in `.env`: `QDRANT_URL=http://localhost:6333`. Leave `QDRANT_API_KEY` empty. Then run `python backend/scripts/create_qdrant_collection.py` from the project root (with venv active and `.env` loaded).

---

## Setup Instructions

### Prerequisites

- **Python 3.10+** (3.12 recommended)
- **Node.js 18+** and npm
- **Supabase** account (database) and **Qdrant** (Cloud or local) and **OpenAI** (or Gemini) API key

### 1. Clone and install backend

```bash
git clone <your-repo-url>
cd "Proactive Financial Agent"

cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up database and vector store

- Complete [Setting up Supabase (Database)](#setting-up-supabase-database) and run the schema SQL.
- Complete [Setting up Qdrant (Vector store)](#setting-up-qdrant-vector-store) and run `python scripts/create_qdrant_collection.py` from `backend/`.

### 3. Environment file

From the **project root**:

```bash
cp .env.example .env
```

Edit `.env` and set at least: `DATABASE_URL`, `QDRANT_URL`, `QDRANT_API_KEY` (for Cloud), and `OPENAI_API_KEY`. The backend loads `.env` from the project root.

Optional for frontend: create `frontend/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000` (this is the default if unset). See **[DEPLOYMENT.md](DEPLOYMENT.md)** for free deployment (Vercel + Render) and production env config.

### 4. Frontend

```bash
cd frontend
npm install
```

---

## Run the project locally

After completing [Setup](#setup-instructions), follow these steps. **All paths are from the project root** (the folder that contains `backend/` and `frontend/`). If your folder name has spaces (e.g. `Proactive Financial Agent`), use quotes: `cd "Proactive Financial Agent"`.

### Step 1 – Backend

1. Open a terminal and go to the project root.
2. Activate the backend virtual environment:
   - **Windows (PowerShell or CMD):** `backend\.venv\Scripts\activate`
   - **macOS/Linux:** `source backend/.venv/bin/activate`
3. Go into the backend and start the API:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

4. Confirm the backend is up: open [http://localhost:8000/health](http://localhost:8000/health) — it should return `{"status":"ok"}`.
5. Leave this terminal running. The backend loads `.env` from the **project root**, so ensure `.env` is there (not inside `backend/`).

### Step 2 – Frontend

1. Open a **second terminal** and go to the project root.
2. Install dependencies if you haven't already (`npm install` in `frontend/`).
3. Start the frontend:
   ```bash
   cd frontend
   npm run dev
   ```
4. Open [http://localhost:3000](http://localhost:3000) in your browser.

### Step 3 – Use the app

- **Ingestion** — Upload PDF or Word fact-finds/meeting notes. The app extracts clients and alerts and indexes text for Ask Jarvis.
- **Dashboard** — Use the date picker, “Start here”, overdue follow-ups, and Pulse alerts. Draft emails and mark alerts done.
- **Ask Jarvis** — Use suggestion chips or type questions; answers use structured data plus document search.
- **Pre-meeting brief** — Select a client to get a one-page brief and suggested talking points.

### Step 4 – Optional: clear data

- **Settings** → Clear data (removes clients, alerts, document metadata, Qdrant vectors, and resets in-memory caches).

---

## Repository Layout

```
Proactive Financial Agent/
├── README.md
├── .env.example          # Template; copy to .env (not committed)
├── .gitignore
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI app, CORS, routers
│   │   ├── db.py         # Postgres connection
│   │   ├── routers/      # ingest, monitor, chat, settings
│   │   └── services/     # cache, config, llm_extractor, vector_store
│   ├── migrations/
│   ├── scripts/          # create_qdrant_collection, test_embeddings, test_llm
│   ├── uploads/          # Ingested files (gitignored; .gitkeep committed)
│   ├── requirements.txt
│   └── supabase_schema.sql
├── frontend/
│   ├── pages/            # Dashboard, Ask Jarvis, Brief, Ingestion, Alerts, Settings
│   ├── components/
│   ├── package.json
│   └── ...
└── (optional) Fact Find Mock Data/  # Sample .docx fact-finds – add locally if desired; not in repo
```

No compiled binaries or credentials are committed; `.env` and `backend/uploads/*` are gitignored.
