# Go/no-go checklist: before any real client PII

The release gate from the production-readiness RFC (Week 8). Every line needs a
named sign-off and a date. "Verified" means demonstrated, not believed.

## Isolation & access control

- [ ] RLS isolation suite green against **production configuration** (runtime
      role + policies): `cd backend && pytest tests/test_tenancy_isolation.py tests/test_api_integration.py`
- [ ] `DATABASE_URL` in production points at `kritifin_app` (not postgres);
      `DATABASE_ADMIN_URL` restricted to the CI migration step + password
      manager (never set on Lambda)
- [ ] Manual IDOR probe on production: org B token against org A client id
      returns 404 (clients, alerts, documents, jobs, conversations, audit)
- [ ] Supabase Data API verified inert: anon-key REST request to
      `/rest/v1/clients` returns zero rows / permission error
- [ ] Qdrant spot check: every point carries `org_id`
      (`backfill_qdrant_org.py --dry-run` reports 0 missing)

## Auth (fail closed)

- [ ] Production env: `AUTH_MODE=required`, `ENV=production`; boot refusal
      demonstrated on staging by removing `SUPABASE_URL`
- [ ] Email confirmation required in Supabase Auth settings
- [ ] Password reset flow works end-to-end on staging
- [ ] No `NEXT_PUBLIC_API_KEY` anywhere in Vercel env or built bundle
- [ ] HS256 fallback removed once both environments confirmed on asymmetric
      keys (`SUPABASE_JWT_SECRET` unset)

## Audit & compliance record

- [ ] `audit_log` rows survive a deploy (write → deploy → read)
- [ ] Append-only verified as runtime role (UPDATE/DELETE rejected)
- [ ] AI generations, approvals, client edits, exports, uploads, and
      clear-data all produce events with `request_id` + actor
- [ ] Retention statement (≥ 6 years) reflected in posture env
      (`DATA_RETENTION_DAYS=2190`) and documented for design partners

## Durability & operations

- [ ] Worker-kill drill passed on staging (job retried to completion, no
      duplicate clients/alerts)
- [ ] Rollback drill passed (timed, < 10 min)
- [ ] Supabase Pro + PITR enabled on production; restore drill passed (timed
      against RTO 4h / RPO 1h)
- [ ] Documents verified in Supabase Storage (not container disk): redeploy,
      then re-download an original
- [ ] Uptime checks live on `/health/ready` + frontend, alerting to a channel
      someone actually reads
- [ ] Sentry receiving from both apps with release tags; forced test error
      triaged end-to-end

## Security posture

- [ ] CI green including security scans (gitleaks, pip-audit, npm audit)
- [ ] CORS: explicit production origins only; no credentials mode
- [ ] CSP: production response headers verified (no `unsafe-eval`)
- [ ] Upload abuse cases rejected on staging: wrong magic bytes, oversize,
      zip bomb (guards in `test_safety.py` demonstrated live)
- [ ] Rate limits verified per-org (two orgs, one saturates, other unaffected)
- [ ] `ALLOW_DATA_RESET=false` in production
- [ ] Secrets rotation runbook dry-run completed once
- [ ] [Threat model](security-threat-model.md) accepted-risks reviewed and
      re-signed by founder

## Load & cost

- [ ] k6 baseline recorded on staging (`load/k6-baseline.js`): p95 pulse
      < 800ms, 5xx < 0.5% at 5 orgs × 250 clients
- [ ] LLM spend per active adviser estimated from staging usage; monthly
      budget alarm configured at the provider

## Residual risks acknowledged (sign explicitly)

- [ ] No malware scanning of uploads yet (validation only) — Phase 2
- [ ] OpenAI processes prompts in the US — disclosed via posture endpoint
- [ ] Single-instance in-memory cache — Redis gate documented for >1 instance

**Sign-off:** ______________________  **Date:** ____________
