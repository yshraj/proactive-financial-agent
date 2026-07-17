# Runbook: backups, PITR, and restore drills

## Targets

- **RPO** (max data loss): 1 hour with PITR; 24 hours on daily backups only.
- **RTO** (max time to restore): 4 hours.

## What is backed up where

| Store | Mechanism | Owner action |
|-------|-----------|--------------|
| Postgres (clients, alerts, documents metadata, audit_log, jobs, conversations, tenancy) | Supabase **Pro** daily backups + PITR add-on | Enable Pro + PITR on the production project (required before real client data) |
| Documents (originals) | Supabase Storage `documents` bucket | Included in Supabase infra durability; NOT in DB backups — do not assume a DB restore restores files |
| Qdrant vectors | Weekly snapshot via Qdrant snapshot API (worker cron — Phase 2), plus full rebuild path | Vectors are derivable: re-ingestion from stored originals can rebuild the index |
| Config/secrets | Render env group + Vercel envs | Export a copy to the password manager on every change |

## Restore drill (quarterly; first one before design-partner beta)

1. Supabase → production project → Backups → restore to a **new** project
   (never in place) at a chosen point in time.
2. Create a scratch Render service (or run locally) pointed at the restored DB:
   set `DATABASE_URL`/`DATABASE_ADMIN_URL`, run `alembic upgrade head`
   (should be a no-op), start the API.
3. Verify: `/health/ready` green; sign in; pulse renders; a Client 360 loads;
   `SELECT COUNT(*) FROM audit_log` matches expectation for the restore point.
4. Record timings against RTO/RPO in the ops log; tear the scratch stack down.

## Qdrant loss

Vectors are a derived store. If snapshots are unavailable or stale:

1. Recreate the collection: `python backend/scripts/create_qdrant_collection.py`
   (creates payload indexes too).
2. Re-index from originals: re-run ingestion for stored documents (the
   extraction cache avoids repeat LLM spend within 24h; beyond that this
   costs real tokens — snapshots are cheaper).

## Audit-trail retention

`audit_log` is append-only and retained a minimum of **6 years** (FCA
record-keeping alignment). It is included in Postgres backups; no automatic
deletion exists anywhere in the codebase, and the runtime DB role cannot
delete from it.
