# Runbook: incident response

## Severity levels

- **SEV1** — data exposure across tenants, data loss, or full outage.
  Response: immediate, drop everything. If client data is exposed: suspend the
  API first (set the Lambda's reserved concurrency to 0 — see
  [deploy-and-rollback.md](deploy-and-rollback.md)), assess second. FCA/ICO
  notification duties may apply (see escalation).
- **SEV2** — a core flow broken for all users (ingestion, chat, dashboard) or
  the worker dead with a growing queue. Response: within 1 hour.
- **SEV3** — degraded (slow AI responses, single-feature bug, elevated error
  rate below alerting threshold). Response: next working day.

## Detection

- Uptime monitor on `GET /health/ready` (backend) and the Vercel homepage —
  alerts to the team email/Slack. Configure at Better Stack or UptimeRobot;
  probe every 1–3 min with 2-failure confirmation.
- Sentry: new-issue and error-rate alerts for both apps (release-tagged).
- Weekly ops review: Sentry trends, `jobs` table failures, LLM spend.

## First 15 minutes (any SEV)

1. Acknowledge the alert; note the time (incident log starts now).
2. Check `/health/ready` — it names the failing dependency (database, qdrant,
   llm_configured) and the running migration version.
3. Check Sentry for the triggering release; check the deploy workflow history
   (GitHub Actions) and CloudFormation stack events for a correlated deploy.
4. Correlate with providers: Supabase status, AWS Health Dashboard, Qdrant
   Cloud status, OpenAI status.
5. If a deploy caused it → rollback per
   [deploy-and-rollback.md](deploy-and-rollback.md). If a provider caused it →
   communicate and wait; do not thrash.

## SEV1 cross-tenant exposure specifics

1. Suspend the API service (leaking beats downtime — never the reverse).
2. Preserve evidence: `audit_log` is append-only; export the window
   (`GET /api/compliance/audit/events` as each affected org, or SQL as admin).
3. Identify scope: which orgs, which rows, which time window (request_id ties
   log lines, audit events, and Sentry traces together).
4. Fix, add a failing-then-passing isolation test, redeploy, verify with the
   RLS suite against production config.
5. Escalate to the founder for ICO (72h breach clock) / FCA notification
   assessment. Notify affected firms honestly and fast.

## Data-loss / restore

- Supabase Pro: PITR restore to a new project → repoint `DATABASE_URL`/
  `DATABASE_ADMIN_URL` → `alembic upgrade head` (no-op if current) → verify.
- Qdrant: restore latest snapshot; if snapshots are stale, re-index from
  stored originals (Supabase Storage) via re-ingestion.
- Documents: originals live in Supabase Storage (`documents` bucket,
  org-prefixed) — they are not part of the Postgres restore.

## Post-incident

Within 48 hours write a short blameless review: timeline, root cause, user
impact, what detection missed, and 1–3 concrete follow-ups (each becomes a
tracked task). Store next to this runbook.
