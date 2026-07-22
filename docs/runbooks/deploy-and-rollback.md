# Runbook: deploy, migrations, rollback

## Environments

| Env | Frontend | Backend | Database | Vectors |
|-----|----------|---------|----------|---------|
| Local | `npm run dev` | uvicorn + `AUTH_MODE=demo` | Supabase dev project or local PG | local/dev Qdrant |
| Staging | Vercel preview env | second SAM stack (e.g. `kritifin-backend-staging`) | Supabase staging project | Qdrant staging cluster |
| Production | Vercel production | AWS Lambda `kritifin-backend-api` + `kritifin-backend-worker` ([deploy/aws/template.yaml](../../deploy/aws/template.yaml)) | Supabase prod (Pro plan) | Qdrant Cloud prod |

Environment invariants (enforced by the app at boot):

- Production runs `AUTH_MODE=required`, `ENV=production`,
  `ALLOW_DATA_RESET=false`.
- `DATABASE_URL` is the **kritifin_app** role (RLS enforced);
  `DATABASE_ADMIN_URL` is the postgres role and is used **only** by Alembic
  (the CI migration step) and break-glass access — it is never set on Lambda.

## Normal deploy

1. Merge to `master` with green CI. The deploy workflow
   ([.github/workflows/deploy-backend.yml](../../.github/workflows/deploy-backend.yml))
   only fires after CI succeeds.
2. The workflow runs `alembic upgrade head` as the admin role first. A failed
   migration aborts the deploy — the old release keeps serving.
3. `sam build && sam deploy` updates both Lambda functions atomically
   (CloudFormation rolls back a failed update on its own); a `/health` smoke
   check runs at the end.
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

1. GitHub → Actions → **Deploy backend (AWS Lambda)** → *Run workflow* with
   `ref` = the last good tag/SHA. Tick **skip_migrations** if the release
   being rolled back added a migration (the DB is ahead of the old ref, and
   old-tree Alembic cannot locate the newer revision; the newer schema is
   expand-contract so the old code runs on it unchanged).
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
  take the API down first (set the function's reserved concurrency to 0:
  `aws lambda put-function-concurrency --function-name kritifin-backend-api
  --reserved-concurrent-executions 0`); leaking is strictly worse than
  downtime for an FCA-regulated audience. Restore with
  `delete-function-concurrency`.

## Worker

- `kritifin-backend-worker` (Lambda, `app/lambda_worker.py`) is event-driven:
  async-invoked by the API after each enqueue, re-invoked by the EventBridge
  schedule every 5 minutes, and self-re-invoked when a drain hits its time
  budget with backlog left. Jobs are claimed with `FOR UPDATE SKIP LOCKED`
  and survive interruptions (retried up to 3 attempts, then failed by the
  sweeper, which runs at the start of every drain).
- Deploying or timing out mid-job is safe: the stale lock is re-claimed after
  10 minutes and ingestion handlers are idempotent per (org, content hash).
- Queue health: `SELECT status, COUNT(*) FROM jobs GROUP BY status;` — a
  PENDING count that outlives two schedule ticks means drains are failing;
  check the worker log group for `Job claim failed` / `worker_invoke_failed`.

## Drills (rehearse on staging, record timings)

- Rollback drill: deploy a trivial change, roll it back, verify health. Target < 10 min.
- Restore drill: PITR-restore the staging DB to a fresh project, point a
  scratch API at it, verify the pulse renders. Target < 4 h (RTO), data loss
  ≤ 1 h (RPO with PITR).
- Worker-kill drill: upload a document async, then force-fail the drain
  mid-job (temporarily set the worker's reserved concurrency to 0, or deploy
  over it); confirm the job completes after the stale-lock window without
  duplicate clients/alerts.
