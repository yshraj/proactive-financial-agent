# Release Notes

## Release-candidate hardening pass (28 Jun 2026)

This release moves the project from a single-user hackathon demo toward a
production-quality SaaS front end with a hardened API surface. It focuses on the
work that could be **completed and validated** in this environment: the UI/UX
overhaul (M3), the frontend platform refactor (M2), and the M0 security
lockdown. Larger platform features that require external services are sequenced
next and listed under **Deferred**.

### Highlights
- **Mobile is fixed.** The app was unusable on phones; it now has a responsive
  shell with a slide-in drawer and works across mobile/tablet/desktop.
- **Hardened API.** Shared API-key gate on every route, per-IP rate limits on
  LLM endpoints, an upload size cap, a guarded destructive reset, and security
  headers.
- **Production UI.** A real component library, design tokens, designed
  empty/loading/error states, accessible dialogs, consistent labels, and a real
  settings hub (no more "demo" copy).
- **Healthier codebase.** Centralized typed API client + React Query data layer,
  shared types/formatters, singleton external clients, structured logging, and
  removal of dead code.
- **A real test suite.** 34 Playwright e2e tests across desktop + mobile, green
  and stable.

---

### Added
- Responsive `AppLayout` with mobile drawer nav, skip-to-content link, account chrome.
- UI component library: `Button`, `Badge`, `Card`/`CardHeader`, `Skeleton`/`DashboardSkeleton`/`TableSkeleton`, `EmptyState`, `ErrorState`, `ErrorBoundary`, accessible `Modal`, and a `Toast` system.
- Frontend platform: `lib/api.ts` (typed client, timeouts, typed errors, optional API key), `lib/types.ts`, `lib/labels.ts`, `lib/format.ts`, and React Query hooks in `hooks/useApi.ts`.
- Design tokens: a `brand` palette and skeleton shimmer in Tailwind; focus-visible rings and `prefers-reduced-motion` support in global CSS.
- Backend security layer: `app/security.py` (API-key dependency, rate limiter, data-reset flag), `app/logging_config.py`, request-id + security-headers middleware, and `app/services/clients.py` singletons.
- Playwright harness: `playwright.config.ts`, a self-contained Node mock backend (`e2e/mock-server.mjs`), and `e2e/*.spec.ts` (smoke, navigation, dashboard, chat, brief, alerts, ingestion, settings) on desktop + mobile.
- `npm` scripts: `typecheck`, `test:e2e`, `mock`. Backend unit test `tests/test_security.py`.

### Changed
- All pages refactored onto the shared client/hooks/components with designed states and accessibility improvements.
- Alerts/Dashboard now share one humanized label map (no raw enum strings).
- Ingestion shows honest upload status instead of fake timed progress.
- Settings is a structured hub; destructive "Clear all data" requires typing `DELETE`.
- `next` upgraded `14.2.15 → 14.2.33`; non-breaking `npm audit fix` applied.
- Emoji icons replaced with a consistent Lucide icon set; favicon + OG/meta added.

### Removed
- The "backend waking up" demo toast (replaced by per-query states).
- Unused `sqlalchemy` dependency; dead "seed script" references.

### Security
- API-key gate on `/api/*`; destructive reset double-gated (`ALLOW_DATA_RESET` + key).
- Per-IP rate limiting on chat/brief/draft/upload; 20 MB bounded upload reads.
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-Request-ID`.

### New environment variables (backend)
| Var | Default | Purpose |
|-----|---------|---------|
| `API_KEY` | _(unset)_ | If set, required as `X-API-Key` on all `/api/*` requests. |
| `ALLOW_DATA_RESET` | `false` | Must be `true` to allow `clear-data`. |
| `MAX_UPLOAD_BYTES` | `20971520` | Upload size cap. |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |

Frontend (optional): `NEXT_PUBLIC_API_KEY` forwards the key from the browser during the M0 stopgap.

### Breaking changes
- If `API_KEY` is set on the backend, clients must send `X-API-Key` (set `NEXT_PUBLIC_API_KEY` for the web app). With it unset, behaviour is unchanged (a warning is logged).
- `clear-data` returns `403` unless `ALLOW_DATA_RESET=true`.

---

### Deferred (blocked on external services / next runs) — see `IMPLEMENTATION_PLAN.md`
- **M1 — real authentication + multi-tenancy + RLS.** Requires provisioning an auth provider (Supabase/Clerk) and a live database; implementing untested auth across every route without a DB would risk regressions, so it is the next milestone. The M0 API-key gate is an interim safeguard, **not** a substitute.
- **M2 backend infra** that needs services: Redis-backed cache and async ingestion queue (a live DB/Redis is unavailable here).
- **M4/M5/M6/M7** — billing, audit/DSAR, streaming/memory, integrations.

### Known limitations / environment notes
- The backend could not be run end-to-end here (the environment only has Python 3.9, while the app targets 3.10+, and there were no DB/Qdrant/OpenAI credentials). Backend changes were validated by syntax/compile and a security unit check; the e2e suite exercises the frontend against a mock backend.
- 2 transitive npm advisories remain that only a breaking Next 16 upgrade resolves; they affect features this app doesn't use.
- Playwright browsers: due to a sandbox cache/arch quirk, run e2e with `PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"` if the default cache mismatches.
