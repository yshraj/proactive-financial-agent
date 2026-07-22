# Runbook: secrets inventory and rotation

Never commit secrets. Local dev uses root `.env` (gitignored); staging and
production use GitHub Actions repository secrets (fed into the Lambda stack at
deploy time as NoEcho CloudFormation parameters) and Vercel project settings.
CI scans every push with gitleaks.

## Inventory

| Secret | Where used | Rotation | Cadence |
|--------|-----------|----------|---------|
| `DATABASE_URL` (kritifin_app password) | api+worker Lambdas | `ALTER ROLE kritifin_app PASSWORD '...'` then update the GitHub secret, redeploy | 90 days / on suspicion |
| `DATABASE_ADMIN_URL` (postgres password) | CI migration step, break-glass | Supabase Dashboard → Database → reset password | 90 days |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend storage access | Supabase → Settings → API → rotate service role | 90 days |
| `SUPABASE_JWT_SECRET` (legacy HS256 only) | JWT verification | Supabase rotates; prefer JWKS (SUPABASE_URL) and drop this | remove when off HS256 |
| `OPENAI_API_KEY` | LLM + embeddings | platform.openai.com → new key → swap → revoke old | 90 days |
| `QDRANT_API_KEY` | Vector store | Qdrant Cloud → API keys | 90 days |
| `SENTRY_DSN` | Error reporting | Not secret-critical; rotate on leak | on leak |
| `API_KEY` (service credential) | Uptime probe / scripts | Generate 32+ random bytes, update callers | 90 days |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Browser | Public by design; RLS + revoked table grants make it inert | n/a |

## Rotation procedure (zero-downtime)

1. Create the new credential at the provider (old one still valid).
2. Update the GitHub Actions secret / Vercel env; trigger redeploy (the deploy
   workflow re-applies all parameters to the Lambda stack).
3. Verify `/health/ready` and one authenticated request.
4. Revoke the old credential.
5. Note the rotation (date, secret, operator) in the ops log.

## Leak response

1. Revoke immediately (before redeploying — broken deploys are recoverable,
   leaked credentials are not).
2. Rotate per above; audit provider logs for use of the leaked credential.
3. If client data could have been accessed → incident-response runbook, SEV1.
4. Purge from git history if committed (BFG/`git filter-repo`) and force-push
   with team coordination; gitleaks in CI should have caught it first.
