# Deployment guide – KritiFin (Proactive Financial Agent)

Production deploys the **frontend on Vercel** and the **backend on AWS Lambda**
(container images, deployed by the SAM stack in [deploy/aws/](deploy/aws/)),
with **Supabase** (Postgres + Auth + Storage) and **Qdrant Cloud** (vectors).
Operational procedures live in [docs/runbooks/](docs/runbooks/).

Designed to run inside the AWS Lambda free tier for demo-level traffic: no
VPC, no NAT Gateway, no API Gateway, no always-on compute.

---

## Overview

| Part | Service | Notes |
|------|---------|-------|
| Frontend | **Vercel** | Next.js; `NEXT_PUBLIC_API_URL` points at the Lambda Function URL |
| Backend API | **Lambda `kritifin-backend-api`** | FastAPI + uvicorn behind the Lambda Web Adapter; public Function URL; 1024 MB / 180 s |
| Background worker | **Lambda `kritifin-backend-worker`** | Event-driven queue drain; async-invoked by the API after each enqueue; 1024 MB / 900 s; reserved concurrency 1 |
| Safety net | **EventBridge Scheduler** | `rate(5 minutes)` → worker; covers missed triggers, stale-lock retries, sweeps |
| Database | **Supabase** | Postgres with RLS; transaction-mode pooler (Lambda-friendly) |
| Auth | **Supabase Auth** | `AUTH_MODE=required` in production |
| Documents | **Supabase Storage** | Private `documents` bucket, org-prefixed keys |
| Vector DB | **Qdrant Cloud** | `client_memory` collection with tenant payload indexes |

```
                         ┌─────────────────────────── AWS (no VPC) ───────────────────────────┐
 Browser ── Vercel       │                                                                    │
    │       (Next.js)    │   ┌─────────────────┐  invoke (Event)   ┌──────────────────────┐   │
    └── HTTPS ───────────┼──▶│ API Lambda      │ ─────────────────▶│ Worker Lambda        │   │
        Function URL     │   │ FastAPI+uvicorn │                   │ drain job queue      │   │
                         │   │ via Web Adapter │     ┌────────────▶│ (SKIP LOCKED claims) │   │
                         │   └────────┬────────┘     │ rate(5 min) └──────┬───────┬───────┘   │
                         │            │        EventBridge Scheduler      │  self-invoke      │
                         │            │                                   │  on backlog       │
                         └────────────┼───────────────────────────────────┼───────────────────┘
                                      ▼                                   ▼
                          Supabase (Postgres+Storage+Auth) · Qdrant Cloud · OpenAI
```

**How ingestion flows:** `POST /api/ingest/upload-async` stores the file,
enqueues a durable job in Postgres, then async-invokes the worker Lambda
(fire-and-forget). The worker claims jobs with `claim_next_job()`
(`FOR UPDATE SKIP LOCKED`), runs LLM extraction → embeddings → Qdrant upsert,
updates job status, and keeps draining until the queue is empty — handing off
to a fresh invocation of itself if it nears the 15-minute limit. The 5-minute
schedule re-drains as a safety net, retries stale jobs, and sweeps exhausted
ones. There is **no polling loop and no always-on process anywhere**.

---

## One-time AWS setup

### 0. AWS account

- **Free-tier note (accounts created after 15 July 2025):** the perpetual
  Lambda allowance (1M requests + 400K GB-s/month) applies on the **paid
  plan** (card on file). The "free plan" expires after 6 months and then
  closes the account — fine for a trial, wrong for hosting this app.
- Create a **budget alert** so surprises page you, not your card:
  ```bash
  aws budgets create-budget --account-id <ACCOUNT_ID> --budget '{
    "BudgetName": "kritifin-monthly", "BudgetLimit": {"Amount": "5", "Unit": "USD"},
    "TimeUnit": "MONTHLY", "BudgetType": "COST"}' \
    --notifications-with-subscribers '[{
      "Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
                       "Threshold": 20, "ThresholdType": "PERCENTAGE"},
      "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "you@example.com"}]}]'
  ```
- Region: everything below assumes `eu-west-2` (London — matches the UK data
  posture). Change `region` in [deploy/aws/samconfig.toml](deploy/aws/samconfig.toml)
  and the `AWS_REGION` repo variable together if you pick another.
- **Concurrency preflight (do this before the first deploy):** the stack
  reserves concurrency for both functions (API cap 10, worker 1), and Lambda
  requires 100 *unreserved* executions to remain — so the account's total
  concurrency limit must be ≥ 111. New accounts often start at **10**, which
  makes the first deploy fail with a confusing CloudFormation error. Check:
  ```bash
  aws lambda get-account-settings \
    --query 'AccountLimit.ConcurrentExecutions' --region eu-west-2
  ```
  If it prints less than 111, either request a quota increase to 1,000
  (Service Quotas → AWS Lambda → "Concurrent executions" — usually approved in
  a day), or set the repo variables `API_RESERVED_CONCURRENCY` and
  `WORKER_RESERVED_CONCURRENCY` to `-1` to deploy without reservations
  (correctness is unaffected — queue claims are `FOR UPDATE SKIP LOCKED` —
  you just lose the hard cost caps; restore them once the quota is raised).

### 1. ECR repository (container images)

```bash
aws ecr create-repository --repository-name kritifin-backend --region eu-west-2

# Keep only recent images: ~2 deploys × 2 images ≈ under the 500 MB ECR free tier.
aws ecr put-lifecycle-policy --repository-name kritifin-backend --region eu-west-2 \
  --lifecycle-policy-text '{"rules":[{"rulePriority":1,"description":"keep last 4 images",
    "selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":4},
    "action":{"type":"expire"}}]}'
```

The repository URI (`<ACCOUNT_ID>.dkr.ecr.eu-west-2.amazonaws.com/kritifin-backend`)
becomes the `AWS_ECR_REPOSITORY` GitHub secret.

### 2. GitHub OIDC deploy role (no long-lived AWS keys)

Create the GitHub OIDC identity provider (once per account):

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

Create the deploy role with a trust policy pinned to this repository:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:<OWNER>/proactive-financial-agent:*"}
    }
  }]
}
```

Permissions policy for the role (least privilege, scoped to this stack's
resource names; if a deploy fails with `AccessDenied`, the error names the
missing action — add it here rather than widening a wildcard):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "CloudFormation", "Effect": "Allow",
     "Action": "cloudformation:*",
     "Resource": ["arn:aws:cloudformation:*:<ACCOUNT_ID>:stack/kritifin-backend/*",
                   "arn:aws:cloudformation:*:<ACCOUNT_ID>:stack/aws-sam-cli-managed-default*"]},
    {"Sid": "SamArtifacts", "Effect": "Allow",
     "Action": ["s3:CreateBucket", "s3:PutObject", "s3:GetObject", "s3:ListBucket",
                 "s3:GetBucketPolicy", "s3:PutBucketPolicy", "s3:PutBucketVersioning",
                 "s3:PutEncryptionConfiguration", "s3:GetEncryptionConfiguration",
                 "s3:PutBucketPublicAccessBlock", "s3:PutBucketTagging", "s3:PutLifecycleConfiguration"],
     "Resource": "arn:aws:s3:::aws-sam-cli-managed-default*"},
    {"Sid": "EcrAuth", "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
    {"Sid": "EcrPush", "Effect": "Allow",
     "Action": ["ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:InitiateLayerUpload",
                 "ecr:PutImage", "ecr:UploadLayerPart", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
                 "ecr:DescribeRepositories", "ecr:DescribeImages"],
     "Resource": "arn:aws:ecr:*:<ACCOUNT_ID>:repository/kritifin-backend"},
    {"Sid": "Lambda", "Effect": "Allow",
     "Action": ["lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction",
                 "lambda:GetFunctionConfiguration", "lambda:UpdateFunctionCode",
                 "lambda:UpdateFunctionConfiguration", "lambda:AddPermission", "lambda:RemovePermission",
                 "lambda:GetPolicy", "lambda:CreateFunctionUrlConfig", "lambda:UpdateFunctionUrlConfig",
                 "lambda:DeleteFunctionUrlConfig", "lambda:GetFunctionUrlConfig",
                 "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency",
                 "lambda:GetFunctionCodeSigningConfig", "lambda:ListVersionsByFunction",
                 "lambda:TagResource", "lambda:UntagResource", "lambda:ListTags"],
     "Resource": "arn:aws:lambda:*:<ACCOUNT_ID>:function:kritifin-backend-*"},
    {"Sid": "LogsScoped", "Effect": "Allow",
     "Action": ["logs:CreateLogGroup", "logs:PutRetentionPolicy", "logs:DeleteLogGroup",
                 "logs:TagResource", "logs:ListTagsForResource"],
     "Resource": "arn:aws:logs:*:<ACCOUNT_ID>:log-group:/aws/lambda/kritifin-backend-*"},
    {"Sid": "LogsDescribe", "Effect": "Allow",
     "Action": "logs:DescribeLogGroups", "Resource": "*"},
    {"Sid": "Scheduler", "Effect": "Allow", "Action": "scheduler:*",
     "Resource": ["arn:aws:scheduler:*:<ACCOUNT_ID>:schedule/*", "arn:aws:scheduler:*:<ACCOUNT_ID>:schedule-group/*"]},
    {"Sid": "Alarms", "Effect": "Allow",
     "Action": ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:DescribeAlarms",
                 "cloudwatch:TagResource", "cloudwatch:ListTagsForResource"],
     "Resource": "arn:aws:cloudwatch:*:<ACCOUNT_ID>:alarm:kritifin-backend-*"},
    {"Sid": "AlertTopic", "Effect": "Allow",
     "Action": ["sns:CreateTopic", "sns:DeleteTopic", "sns:GetTopicAttributes", "sns:SetTopicAttributes",
                 "sns:Subscribe", "sns:Unsubscribe", "sns:ListSubscriptionsByTopic",
                 "sns:TagResource", "sns:ListTagsForResource"],
     "Resource": "arn:aws:sns:*:<ACCOUNT_ID>:kritifin-backend-*"},
    {"Sid": "FunctionRoles", "Effect": "Allow",
     "Action": ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
                 "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy",
                 "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:TagRole", "iam:UntagRole",
                 "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"],
     "Resource": "arn:aws:iam::<ACCOUNT_ID>:role/kritifin-backend-*"}
  ]
}
```

(For a throwaway personal account, `PowerUserAccess` plus the `FunctionRoles`
statement is the pragmatic shortcut — but prefer the scoped policy above.)

The role ARN becomes the `AWS_DEPLOY_ROLE_ARN` GitHub secret.

For reference, the **runtime** IAM the stack creates for itself is minimal:
the API function may only `lambda:InvokeFunction` the worker; the worker may
only re-invoke itself; both write CloudWatch Logs. No other AWS access exists
(Supabase/Qdrant/OpenAI are plain HTTPS).

### 3. GitHub secrets and variables

Repository **secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|-------|
| `AWS_DEPLOY_ROLE_ARN` | OIDC deploy role ARN from step 2 |
| `AWS_ECR_REPOSITORY` | ECR repository URI from step 1 |
| `DATABASE_URL` | Supabase pooler URI (Transaction mode, port 6543) **as `kritifin_app`** |
| `DATABASE_ADMIN_URL` | pooler URI as `postgres` — used **only** by the CI migration step, never set on Lambda |
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | service role key (Storage; server-side only) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Qdrant Cloud cluster |
| `OPENAI_API_KEY` | LLM + embeddings |
| `SENTRY_DSN` | backend Sentry project (optional) |
| `ACCESS_CODE` | only for demo-posture deploys (optional) |

Repository **variables**:

| Variable | Value |
|----------|-------|
| `AWS_REGION` | `eu-west-2` (default if unset) |
| `CORS_ORIGINS` | your Vercel URL(s), comma-separated, no trailing slash |
| `BACKEND_ENV_NAME` | `production` (default) — or `demo`/`staging` |
| `BACKEND_AUTH_MODE` | `required` (default) — or `demo` (refused when ENV=production) |
| `API_RESERVED_CONCURRENCY` | default `10` — hard cap on concurrent API executions (cost/DoS bound); `-1` disables (see concurrency preflight) |
| `WORKER_RESERVED_CONCURRENCY` | default `1` — serialises worker drains; `-1` disables |
| `ALERT_EMAIL` | optional — email for CloudWatch alarm notifications (confirm the SNS subscription email after the first deploy) |

### 4. Supabase

1. Create the project (choose a UK/EU region for residency).
2. Note the pooler URI (Project Settings → Database → **Transaction mode**,
   port 6543) — Lambda opens short-lived connections, so transaction pooling
   is required, and it's what the app already expects.
3. Run migrations from your machine as the admin role:
   ```bash
   cd backend
   DATABASE_ADMIN_URL="postgresql://postgres...:PASSWORD@...pooler.supabase.com:6543/postgres" \
     alembic upgrade head
   ```
4. Enable the runtime role's login (SQL editor, as postgres):
   ```sql
   ALTER ROLE kritifin_app LOGIN PASSWORD '<generate a strong password>';
   ```
5. Storage: no manual step — the backend creates the private `documents`
   bucket on first upload using `SUPABASE_SERVICE_ROLE_KEY`.
6. Auth: enable email confirmation (Authentication → Providers → Email).

### 5. Qdrant Cloud

1. Create a cluster; note URL + API key.
2. Create the collection **with tenant payload indexes**:
   ```bash
   python backend/scripts/create_qdrant_collection.py
   ```

### 6. First deploy + Vercel

1. Push to `master` with green CI (or run the **Deploy backend (AWS Lambda)**
   workflow manually). The workflow migrates the DB, builds both images, and
   deploys the stack. The **ApiUrl** stack output is printed at the end —
   an URL like `https://<id>.lambda-url.eu-west-2.on.aws`.
2. Vercel: import the repo, Root Directory = `frontend`, and set:
   - `NEXT_PUBLIC_API_URL` = the Function URL (no trailing slash)
   - `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` (auth)
   - `NEXT_PUBLIC_SENTRY_DSN` (optional)
3. Set the `CORS_ORIGINS` repo variable to the Vercel URL and redeploy the
   backend (CORS is enforced by FastAPI, passed in at deploy time).

### 7. Monitoring

1. Uptime: create checks on `GET <ApiUrl>/health/ready` and the Vercel
   homepage (Better Stack / UptimeRobot free tier). This doubles as a
   keep-warm ping that reduces cold starts.
2. Sentry: one project per app; alert rules for new issues + error-rate spikes.
3. CloudWatch alarms (created by the stack, free tier): worker `Errors ≥ 1`
   and API `Errors ≥ 5` per 5 minutes. Set the `ALERT_EMAIL` repo variable to
   get email notifications via SNS — then **confirm the subscription email**
   AWS sends after the first deploy, or notifications stay silent. Worker
   *throttles* are intentionally not alarmed: with reserved concurrency 1
   they are routine (throttled triggers queue and retry automatically).

---

## Every deploy after that

Merge to `master` with green CI. The deploy workflow runs `alembic upgrade
head` (expand-contract — the still-running old release keeps working), then
`sam build && sam deploy`. Vercel builds the frontend from the same merge.

Deploy from a laptop instead (uses your local AWS credentials):

```bash
cd deploy/aws
sam build
sam deploy \
  --image-repository <ACCOUNT_ID>.dkr.ecr.eu-west-2.amazonaws.com/kritifin-backend \
  --parameter-overrides \
    "DatabaseUrl=$DATABASE_URL" "QdrantUrl=$QDRANT_URL" "QdrantApiKey=$QDRANT_API_KEY" \
    "OpenAiApiKey=$OPENAI_API_KEY" "SupabaseUrl=$SUPABASE_URL" \
    "SupabaseServiceRoleKey=$SUPABASE_SERVICE_ROLE_KEY" "SentryDsn=$SENTRY_DSN" \
    "CorsOrigins=https://your-app.vercel.app"
```

Tail logs / inspect the queue:

```bash
sam logs --stack-name kritifin-backend --region eu-west-2 --tail   # both functions
# Queue health (psql against the pooler):
#   SELECT status, COUNT(*) FROM jobs GROUP BY status;
```

---

## Migrating from Render (cutover order)

1. Complete the one-time setup above and deploy the stack while Render still
   serves production traffic.
2. Validate the Lambda API directly against the Function URL (checklist
   below) — same database, same Qdrant, so behaviour is identical.
3. Flip `NEXT_PUBLIC_API_URL` on Vercel to the Function URL; redeploy the
   frontend. Update `CORS_ORIGINS` if the frontend URL changed.
4. **Suspend** (don't delete) the Render services. Render's polling worker
   and the Lambda worker can even coexist safely during the transition —
   queue claims are `FOR UPDATE SKIP LOCKED`.
5. After a quiet week, delete the Render services.

## Rollback

- **Backend, bad release:** run the deploy workflow via *workflow_dispatch*
  with `ref` = the last good tag/SHA. **If the bad release added a database
  migration, also tick `skip_migrations`** — the DB is then ahead of the
  target ref and `alembic upgrade head` from the old tree would abort with
  "Can't locate revision"; skipping is safe because schema changes are
  expand-contract. CloudFormation also auto-rolls-back failed deploys on its
  own.
- **Backend, bad platform day:** point `NEXT_PUBLIC_API_URL` back at the
  suspended-then-resumed Render service (kept during the transition window).
- **Schema (rare):** `DATABASE_ADMIN_URL=<admin url> alembic downgrade -1`,
  then redeploy the matching code release.
- **Full teardown:** `sam delete --stack-name kritifin-backend` (Supabase and
  Qdrant are untouched).

## Post-deploy testing checklist

- [ ] `GET <ApiUrl>/health` → `{"status":"ok"}`; `GET <ApiUrl>/health/ready` → 200
- [ ] Access gate: `/api/access/check` → 401 without credentials, 200 with
- [ ] Upload: `POST /api/ingest/upload-async` → 202 with `job_id`; poll
      `GET /api/ingest/jobs/{id}` → PROCESSING (worker log shows
      `reason=upload-enqueued`) → DONE; client + alerts appear
- [ ] Duplicate upload of the same file → 409 DUPLICATE
- [ ] Oversized upload (> 4 MB) → clean 413 from the app
- [ ] Copilot chat + meeting brief answer with citations (long LLM call
      inside the 180 s API timeout)
- [ ] Worker safety net: within 5 minutes CloudWatch shows a scheduled drain
      (`reason=schedule`, `processed=0`)
- [ ] Kill-mid-job drill: enqueue an upload, deploy (or throttle) mid-run —
      job is re-claimed after the 10-minute stale window, no duplicate
      clients/alerts (idempotent per org + content hash)
- [ ] Logs are JSON with `request_id`/`org_id`; log groups show 14-day retention
- [ ] Both CloudWatch alarms exist and are in OK state; if `ALERT_EMAIL` is
      set, the SNS subscription email has been confirmed
- [ ] Budget alert exists; Cost Explorer shows $0 Lambda charges

## Free-tier cost model (demo traffic)

| Item | Monthly usage | Free allowance |
|------|--------------|----------------|
| API requests | thousands | 1M requests |
| API compute (1 GB, LLM-bound seconds per call) | a few thousand GB-s | 400K GB-s (shared) |
| Worker: scheduled no-op drains | ~8,640 × <1 s × 1 GB ≈ 9K GB-s | " |
| Worker: real ingestions (minutes each) | tens–hundreds | " |
| EventBridge Scheduler | ~8,640 invocations | 14M |
| CloudWatch Logs (14-day retention) | well under 5 GB ingest | 5 GB |
| CloudWatch alarms + SNS email alerts | 2 alarms, a few emails | 10 alarms / 1,000 emails |
| ECR storage (lifecycle keeps 4 images) | ≈ free-tier boundary | 500 MB private |

Fixed monthly charges: none. The only always-on things are a Postgres row
queue (Supabase free tier) and a cron schedule (free). Known trade-offs of
staying free: cold starts of a few seconds after idle (the UI shows a
"Starting the service…" notice instead of appearing frozen), and the 4 MB
upload cap (`MAX_UPLOAD_BYTES` — the Function URL payload limit is ~6 MB;
raise it only if you move uploads to direct-to-Storage presigned URLs). The
UI reads `GET /api/ingest/limits`, so the upload screen shows the real 4 MB
limit and oversized files get a friendly message on this deployment
automatically.

## Local development

- `.env` at project root (`cp .env.example .env`), `AUTH_MODE=demo` for open
  local mode. Async uploads are drained by an in-process background task
  right after each upload — no worker process, no `WORKER_FUNCTION_NAME`.
- Apply migrations to your dev database: `cd backend && alembic upgrade head`.
- Validate configuration any time: `python backend/scripts/check_env.py --connect`.
