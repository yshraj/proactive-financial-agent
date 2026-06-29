# Security Audit — KritiFin

Complete security, validation, and robustness audit. Defensive fixes applied without changing core product behaviour.

## Endpoint Inventory

| Method | Path | Auth | Rate limit | Notes |
|--------|------|------|------------|-------|
| GET | `/health` | None | — | Public liveness |
| GET | `/api/ingest/documents` | API key + JWT* | 120/min default | Lists all documents |
| POST | `/api/ingest/upload` | API key + JWT* | 30/min | PDF/DOCX + magic-byte validation |
| POST | `/api/chat/` | API key + JWT* | 30/min | Query max 2000 chars |
| POST | `/api/chat/brief` | API key + JWT* | 30/min | Client validation → 404 |
| GET | `/api/monitor/clients` | API key + JWT* | 120/min default | Global book |
| GET | `/api/monitor/clients/{id}` | API key + JWT* | 30/min | LLM summary on miss |
| GET | `/api/monitor/pulse` | API key + JWT* | 120/min default | Dashboard |
| GET | `/api/monitor/digest` | API key + JWT* | 30/min | LLM digest |
| GET | `/api/monitor/alerts` | API key + JWT* | 120/min default | Filtered alerts |
| GET | `/api/monitor/completed` | API key + JWT* | 120/min default | Completed alerts |
| PATCH | `/api/monitor/alerts/{id}/status` | API key + JWT* | **60/min** (new) | Status mutation |
| POST | `/api/monitor/draft-email` | API key + JWT* | 30/min | LLM draft |
| POST | `/api/settings/clear-data` | API key + JWT* + `ALLOW_DATA_RESET` | **3/hour** (new) | Destructive wipe |

\*When `API_KEY` and/or Supabase JWT vars are unset, auth is open (dev/CI mode). Production startup now fails if `ENV=production` and no auth is configured.

---

## Security Findings

### Critical (documented; M1 scope)

| Finding | Risk | Status |
|---------|------|--------|
| No tenant isolation / IDOR | Any authenticated user sees entire book | **Open** — requires M1 RLS + workspace scoping |
| Auth optional when env unset | Accidental open API in production | **Mitigated** — `require_auth_in_production()` at startup |
| Cross-user LLM cache leakage | Shared cache keys across JWT users | **Mitigated** — chat cache keyed by `user.id` |
| `NEXT_PUBLIC_API_KEY` in browser | Key extractable from JS bundle | **Open** — document; proxy via server routes for prod |

### High (partially fixed)

| Finding | Fix applied |
|---------|-------------|
| Prompt injection via chat query | `<user_query>` delimiters, length cap (2000), system prompt hardening |
| Prompt injection via documents | RAG content sanitization, untrusted-data labels in prompts |
| Open redirect (`//evil.com`) | `safeRedirectPath()` allowlist on login/signup |
| XSS via markdown links | `isSafeHref()` — only http(s) and `#source-N`; images disabled |
| XSS via brief PDF export | `escapeHtml()` on client name in print template |
| Internal errors in API responses | Generic messages for settings clear, ingest extraction |
| Extension-only upload validation | Magic-byte validation (PDF `%PDF-`, DOCX `PK\x03\x04`) client + server |
| Missing rate limits | Global 120/min default; PATCH 60/min; clear-data 3/hour |
| Timing attack on API key | `secrets.compare_digest()` |

### Medium (partially fixed)

| Finding | Fix applied |
|---------|-------------|
| Unbounded Pydantic inputs | `Field(max_length=...)` on chat/brief models |
| Brief returns 200 for missing client | Now returns 404 before LLM |
| No CSP on frontend | Security headers in `next.config.js` |
| 500 errors forwarded to UI | Generic message in production (`lib/api.ts`) |
| Client upload MIME unchecked | MIME allowlist + magic bytes on admin page |

### Low / Informational

| Finding | Notes |
|---------|-------|
| SQL injection | **None found** — all queries parameterized |
| CSRF | Bearer-token auth (not cookie) — low CSRF risk today |
| JWT verification | Algorithm-pinned, issuer/audience checked |
| `/health` public | Acceptable |
| MD5 for cache hashing | Non-crypto use only |
| Next.js 14.2.x advisories | Upgrade to patched 15.5.x+ recommended |

---

## Fixes Applied

### Backend
- `app/services/safety.py` — sanitization, magic-byte validation, public error messages
- `app/security.py` — constant-time API key, production auth gate, global rate limit
- `app/main.py` — startup auth check
- `app/services/prompts.py` — injection-resistant delimiters and instructions
- `app/services/rag_context.py` — strip injection patterns from retrieved chunks
- `app/routers/chat.py` — input validation, user-scoped cache keys, brief 404
- `app/routers/ingest.py` — magic-byte validation, generic processing errors
- `app/routers/settings.py` — generic errors, rate limit
- `app/routers/monitor.py` — rate limit on alert status PATCH
- `tests/test_safety.py` — unit tests for safety helpers

### Frontend
- `lib/safeRedirect.ts` — open redirect prevention
- `lib/sanitize.ts` — HTML escape, safe href, upload magic-byte check
- `components/ai/AiMarkdown.tsx` — safe links, no images
- `pages/login.tsx`, `pages/signup.tsx` — safe redirects
- `pages/brief.tsx` — escaped print export
- `pages/admin.tsx` — MIME + magic-byte client validation
- `lib/api.ts` — generic 500 messages in production
- `next.config.js` — CSP and security headers

---

## Remaining Risks

1. **Multi-tenancy / authorization** — highest priority for production; planned M1
2. **`NEXT_PUBLIC_API_KEY`** — must not be used in production; use server-side proxy
3. **Token streaming not implemented** — no change to attack surface but UX gap
4. **In-memory cache** — not shared across workers; use Redis with tenant prefix in prod
5. **Book-wide RAG search** — intentional for demo; privacy risk with multi-adviser deployment
6. **Document prompt injection** — pattern stripping reduces but does not eliminate adversarial docs
7. **Dependency vulnerabilities** — Next.js 14.x has published advisories; upgrade path needed
8. **Brief print export** — still uses `innerHTML` for brief body (LLM output); markdown links now sanitized at render time

---

## Recommendations

| Priority | Recommendation |
|----------|----------------|
| P0 | Implement M1 tenancy: Postgres RLS, Qdrant tenant filter, cache tenant prefix |
| P0 | Remove `NEXT_PUBLIC_API_KEY`; proxy API through Next.js Route Handlers |
| P1 | Upgrade Next.js to patched 15.5.x+ |
| P1 | Add `rehype-sanitize` for defense-in-depth on markdown |
| P1 | Redis cache with user/workspace prefix for multi-instance deployments |
| P2 | Audit logging for cross-client queries and mutations |
| P2 | ClamAV or similar malware scan on uploads |
| P2 | Extend `check_env.py` to validate Supabase auth vars in production |
| P3 | Generic login error messages (prevent user enumeration) |
| P3 | Admin confirmation token for `clear-data` |

---

## Verification

- `backend/tests/test_safety.py` — safety helper unit tests
- `backend/tests/test_security.py` — existing auth gate tests
- `npm run build` — passes with CSP headers
- `npm run test:e2e -- --project=chromium` — regression check
