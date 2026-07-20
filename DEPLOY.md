# DEPLOY.md — KritiFin on a single VM with Docker

Self-hosted deployment of the KritiFin stack (Caddy → Next.js frontend + FastAPI
backend) on one Linux VM. Postgres (Supabase), Qdrant (Qdrant Cloud), and the
LLM (OpenAI/Gemini) are **external managed services**.

Following this file from a clean VM gets the stack running end to end. For the
managed-PaaS path (Vercel + Render) see [DEPLOYMENT.md](DEPLOYMENT.md) instead.

---

## 0. Before you start — you need

- A Linux VM (Ubuntu 22.04+ recommended), 2 vCPU / 2–4 GB RAM, with a public IP.
- A **domain name** you control (for HTTPS). You'll point it at the VM in step 5.
- SSH access to the VM with sudo.
- Accounts / credentials ready:
  - **Supabase** Postgres connection strings (runtime + admin).
  - **Qdrant Cloud** cluster URL + API key.
  - **OpenAI** API key (or Gemini).
  - A long random **access code** for the demo front door.

---

## 1. Install Docker + Compose (on the VM)

```bash
# Docker Engine + Compose plugin (official convenience script)
curl -fsSL https://get.docker.com | sudo sh

# Run docker without sudo (log out/in afterwards for it to take effect)
sudo usermod -aG docker "$USER"

# Verify
docker version
docker compose version
```

## 2. Firewall — only SSH + HTTP/HTTPS

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Nothing else needs to be open. Postgres and Qdrant are external managed services
(reached outbound over TLS). The backend and frontend container ports are bound
to `127.0.0.1` only — never publicly exposed; Caddy is the sole public entry.

## 3. Clone the repository

```bash
git clone <your-repo-url> kritifin
cd kritifin
```

## 4. Configure environment

```bash
cp .env.production.example .env
nano .env        # fill in real values
```

Fill in **at least** these (the backend logs a warning at startup naming any it
finds unset):

| Var | Value |
|-----|-------|
| `ENV` | `demo` (NOT `production` — demo mode is refused when ENV=production) |
| `AUTH_MODE` | `demo` |
| `ACCESS_CODE` | a long random string (the shared front-door code) |
| `DATABASE_URL` | Supabase runtime connection (kritifin_app role) |
| `DATABASE_ADMIN_URL` | Supabase admin connection (for migrations) |
| `QDRANT_URL` / `QDRANT_API_KEY` | your Qdrant Cloud cluster URL + key |
| `OPENAI_API_KEY` | your OpenAI key (or set `LLM_PROVIDER=gemini` + a Gemini key) |
| `DOMAIN` | your public domain, e.g. `demo.example.com` |
| `ACME_EMAIL` | your email (Let's Encrypt expiry notices) |
| `CORS_ORIGINS` | `https://<DOMAIN>` |
| `NEXT_PUBLIC_API_URL` | `https://<DOMAIN>` (must be the full URL — empty falls back to localhost) |

`.env` is gitignored — keep it on the VM only, never commit it.

## 5. Point DNS at the VM

Create a DNS **A record** for `DOMAIN` → the VM's public IP. Confirm it resolves
before starting Caddy (TLS issuance needs it):

```bash
dig +short <DOMAIN>     # should print the VM's IP
```

## 6. One-off: database migrations

Run once before the first start (and after any release with new migrations).
Uses `DATABASE_ADMIN_URL` from `.env`:

```bash
docker compose run --rm backend alembic upgrade head
```

## 7. One-off: create the Qdrant collection

```bash
docker compose run --rm backend python scripts/create_qdrant_collection.py
```

## 8. Build and start the stack

```bash
docker compose --profile proxy up -d --build
```

This builds the backend + frontend images and starts `backend`, `frontend`, and
`caddy`. Caddy obtains a TLS certificate for `DOMAIN` automatically (first start
can take ~30 s while the cert is issued).

Check health:

```bash
docker compose ps          # all services "running"/"healthy"
docker compose logs -f caddy   # watch for successful certificate issuance
```

## 9. Verify

```bash
# Liveness (public, ungated)
curl -fsS https://<DOMAIN>/health
# -> {"status":"ok"}

# Front-door gate: no code -> 401
curl -s -o /dev/null -w "%{http_code}\n" https://<DOMAIN>/api/access/check
# -> 401

# With the code -> 200
curl -s -H "X-Access-Code: <ACCESS_CODE>" https://<DOMAIN>/api/access/check
# -> {"ok":true}
```

Then open `https://<DOMAIN>` in a browser, enter the access code on the gate
screen, and confirm the dashboard loads. HTTP is redirected to HTTPS.

For a fuller automated pass (gate, pagination clamp, and — opt-in — the rate
limit), plus a manual checklist for restart-survival and chat persistence:

```bash
BASE_URL=https://<DOMAIN> ACCESS_CODE=<ACCESS_CODE> ./deploy/smoke-test.sh
```

---

## Updating to a new release

```bash
cd kritifin
git pull
docker compose run --rm backend alembic upgrade head   # if migrations changed
docker compose --profile proxy up -d --build
```

Compose recreates only changed services. To roll back, `git checkout <prev-tag>`
and re-run the same up command (schema changes are expand-contract, so the
previous release runs on the newer schema).

## Operating

```bash
docker compose logs -f backend        # structured JSON logs (rate-limit hits, errors)
docker compose ps                     # health status
docker compose --profile proxy down   # stop the stack (volumes/certs persist)
docker compose --profile proxy restart backend
```

## Troubleshooting

- **Caddy can't get a cert** — DNS not pointing at the VM yet, or port 80/443
  blocked. Fix DNS/firewall; Caddy retries automatically.
- **Backend logs "CONFIG: … is not set"** — an expected env var is missing; the
  warning names it. Fix `.env` and `docker compose up -d` again.
- **Backend refuses to boot** — `AUTH_MODE=required` without Supabase config, or
  `AUTH_MODE=demo` with `ENV=production`. Set `ENV=demo` and `AUTH_MODE=demo`.
- **Browser API calls fail with CORS / wrong host** — `NEXT_PUBLIC_API_URL` must
  be `https://<DOMAIN>` (it's inlined at build time; rebuild the frontend after
  changing it: `docker compose --profile proxy up -d --build frontend`).
- **Ingestion job stuck** — jobs are durable in Postgres; a job interrupted by a
  restart is reclaimed or failed by the sweeper. Check `docker compose logs backend`.
