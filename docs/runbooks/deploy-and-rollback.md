# Runbook: deploy, migrations, rollback

## Environments

| Env | Frontend | Backend | Database | Vectors |
|-----|----------|---------|----------|---------|
| Local | `npm run dev` | uvicorn + `AUTH_MODE=demo` | Supabase dev project or local PG | local/dev Qdrant |
| Staging | Vercel preview env | Render `kritifin-api-staging` | Supabase staging project | Qdrant staging cluster |
| Production | Vercel production | Render `kritifin-api` + `kritifin-worker` ([render.yaml](../../render.yaml)) | Supabase prod (Pro plan) | Qdrant Cloud prod |

Environment invariants (enforced by the app at boot):

- Production runs `AUTH_MODE=required`, `ENV=production`, `INLINE_WORKER=false`,
  `ALLOW_DATA_RESET=false`.
- `DATABASE_URL` is the **kritifin_app** role (RLS enforced);
  `DATABASE_ADMIN_URL` is the postgres role and is used **only** by Alembic
  (pre-deploy) and break-glass access.

## Normal deploy

1. Merge to `master` with green CI (Render is configured with "Wait for CI").
2. Render builds, then runs `preDeployCommand: alembic upgrade head` as the
   admin role. A failed migration aborts the deploy — the old release keeps
   serving.
3. Zero-downtime rollout gated on `/health/ready` (checks DB, Qdrant, auth
   posture, migration version).
4. Vercel deploys the frontend from the same merge; PR branches get preview
   deployments pointed at the staging API.

## Migration discipline (expand-contract)

- Additive changes only in the release that introduces them (new tables,
  nullable columns, backfills). Destructive steps (drop column/constraint)
  ship at least one release later, once no running code references them.
- Every revision implements a tested `downgrade()`; CI runs
  upgrade → downgrade -1 → upgrade and a full `downgrade base` drill.
- Data migrations are idempotent (safe to re-run).

## Rollback

Code rollback (first resort, safe because of expand-contract):

1. Render dashboard → service → Deploys → previous deploy → **Rollback**.
2. Verify `/health/ready` and Sentry error rate.
3. Frontend: Vercel → Deployments → previous → Promote to production.

Schema rollback (rare; only when a migration itself is the fault):

1. `cd backend && DATABASE_ADMIN_URL=<prod admin url> alembic downgrade -1`
2. Roll code back to the matching release.
3. Post-incident: add a regression test before re-attempting.

Emergency RLS lever (cross-tenant read incident):

- The isolation stack is: RLS policies → org-scoped SQL → org-prefixed caches
  → Qdrant org filter. If a policy bug *blocks legitimate access*, point
  `DATABASE_URL` at the admin role temporarily (owner bypasses RLS) while
  fixing policies — never disable RLS on tables. If a policy bug *leaks*,
  take the API down (`Suspend` in Render) first; leaking is strictly worse
  than downtime for an FCA-regulated audience.

## Worker

- `kritifin-worker` runs `python -m app.worker`; jobs are claimed with
  `FOR UPDATE SKIP LOCKED` and survive restarts (retried up to 3 attempts,
  then failed by the sweeper).
- Deploying the worker mid-job is safe: the stale lock is re-claimed after
  10 minutes and ingestion handlers are idempotent per (org, content hash).
- Queue health: `SELECT status, COUNT(*) FROM jobs GROUP BY status;` — a
  growing PENDING count with a live worker means claims are failing; check
  worker logs for `Job claim failed`.

## Drills (rehearse on staging, record timings)

- Rollback drill: deploy a trivial change, roll it back, verify health. Target < 10 min.
- Restore drill: PITR-restore the staging DB to a fresh project, point a
  scratch API at it, verify the pulse renders. Target < 4 h (RTO), data loss
  ≤ 1 h (RPO with PITR).
- Worker-kill drill: upload a document async, `kill -9` the worker mid-job,
  confirm the job completes after restart without duplicate clients/alerts.
