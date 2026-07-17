# Deployment guide – KritiFin (Proactive Financial Agent)

Production deploys the **frontend on Vercel** and the **backend (API + worker) on
Render** via the checked-in [render.yaml](render.yaml) blueprint, with
**Supabase** (Postgres + Auth + Storage) and **Qdrant Cloud** (vectors).
Operational procedures live in [docs/runbooks/](docs/runbooks/).

---

## Overview

| Part | Service | Notes |
|------|---------|-------|
| Frontend | **Vercel** | Next.js; PR preview deployments point at staging |
| Backend API | **Render web service** | `kritifin-api`; Starter plan (zero-downtime deploys, pre-deploy migrations, no cold starts) |
| Background worker | **Render worker** | `kritifin-worker`; owns the durable ingestion queue |
| Database | **Supabase** | Postgres with row-level security; **Pro plan + PITR for production** (backups runbook) |
| Auth | **Supabase Auth** | Required in production (`AUTH_MODE=required`) |
| Documents | **Supabase Storage** | Private `documents` bucket, org-prefixed keys |
| Vector DB | **Qdrant Cloud** | `client_memory` collection with tenant payload indexes |

Run **staging** as a full copy (second Supabase project, second Qdrant cluster,
Render blueprint deployed from the same repo, Vercel preview env) with
synthetic data only.

---

## One-time production setup

### 1. Supabase

1. Create the project (choose a UK/EU region for residency).
2. Note two connection strings (Project Settings → Database):
   - pooler URI (Transaction mode, port 6543) — used for both roles below.
3. Run migrations from your machine as the admin role:
   ```bash
   cd backend
   DATABASE_ADMIN_URL="postgresql://postgres...:PASSWORD@...pooler.supabase.com:6543/postgres" \
     alembic upgrade head
   ```
   This creates the schema, tenancy tables, RLS policies, and the
   least-privilege `kritifin_app` runtime role.
4. Enable the runtime role's login (SQL editor, as postgres):
   ```sql
   ALTER ROLE kritifin_app LOGIN PASSWORD '<generate a strong password>';
   ```
5. Storage: no manual step — the backend creates the private `documents`
   bucket on first upload using `SUPABASE_SERVICE_ROLE_KEY`.
6. Auth: enable email confirmation (Authentication → Providers → Email).

### 2. Qdrant Cloud

1. Create a cluster; note URL + API key.
2. Create the collection **with tenant payload indexes**:
   ```bash
   python backend/scripts/create_qdrant_collection.py
   ```
3. If migrating an existing collection, backfill tenancy:
   ```bash
   python backend/scripts/backfill_qdrant_org.py
   ```

### 3. Render (blueprint)

1. New → Blueprint → point at this repo; Render reads [render.yaml](render.yaml)
   (API web service + worker).
2. Create the `kritifin-secrets` env group with:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | pooler URI **as `kritifin_app`** (runtime; RLS enforced) |
| `DATABASE_ADMIN_URL` | pooler URI as `postgres` (pre-deploy migrations only) |
| `SUPABASE_URL` | `https://<project>.supabase.co` (JWT verification via JWKS) |
| `SUPABASE_SERVICE_ROLE_KEY` | service role key (Storage; server-side only) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant Cloud cluster |
| `OPENAI_API_KEY` | LLM + embeddings |
| `SENTRY_DSN` | backend Sentry project |
| `CORS_ORIGINS` | your Vercel URL(s), comma-separated, no trailing slash |
| `API_KEY` (optional) | service credential for uptime probes/scripts |

   Non-secret env (`ENV=production`, `AUTH_MODE=required`,
   `INLINE_WORKER=false`, `ALLOW_DATA_RESET=false`, `LOG_FORMAT=json`,
   `PYTHON_VERSION`) is pinned in render.yaml.
3. Settings → enable **"Wait for CI to pass"** so deploys are gated on GitHub CI.
4. Deploys run `alembic upgrade head` as a pre-deploy step; a failed migration
   aborts the rollout and the old release keeps serving.

### 4. Vercel (frontend)

1. Import the repo, Root Directory = `frontend`.
2. Environment variables:
   - `NEXT_PUBLIC_API_URL` = the Render API URL
   - `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` (auth)
   - `NEXT_PUBLIC_SENTRY_DSN` (optional; frontend Sentry project)
3. The anon key is public by design; the database is protected by RLS and
   revoked PostgREST grants, not by hiding the key. There is **no**
   `NEXT_PUBLIC_API_KEY` — browser auth is the Supabase JWT.

### 5. Monitoring

1. Uptime: create checks on `GET <api>/health/ready` and the Vercel homepage
   (Better Stack / UptimeRobot free tier; 1–3 min interval, alert on 2
   consecutive failures).
2. Sentry: one project per app; alert rules for new issues + error-rate spikes.
   CI/Render set `RELEASE_SHA` for release tagging where available.

---

## Every deploy after that

Merge to `master` with green CI. Render migrates + rolls out the backend
(zero downtime, health-gated); Vercel builds the frontend. Rollback and drill
procedures: [docs/runbooks/deploy-and-rollback.md](docs/runbooks/deploy-and-rollback.md).

## Local development

- `.env` at project root (`cp .env.example .env`), `AUTH_MODE=demo` for open
  local mode, `INLINE_WORKER=true` (default) so async ingestion works without
  a separate worker.
- Apply migrations to your dev database: `cd backend && alembic upgrade head`.
- Validate configuration any time: `python backend/scripts/check_env.py --connect`.
