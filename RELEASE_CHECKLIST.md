# Release Checklist

Status: `[x]` done this pass · `[~]` partial · `[ ]` open · `[B]` blocked (external service / next run)

## Code quality & build
- [x] `tsc --noEmit` clean (frontend, incl. e2e)
- [x] ESLint clean on changed files
- [x] Backend syntax/compile clean
- [x] No dead code / unused deps (`sqlalchemy` removed, seed-script refs removed)
- [x] Shared API client + types; no duplicated constants/formatters
- [ ] CI pipeline running lint + typecheck + e2e on PRs

## Testing
- [x] Playwright e2e suite (34 tests, desktop + mobile) green & stable
- [x] Backend security unit check (auth gate + reset flag)
- [~] Component/unit tests (RTL) — to add for primitives
- [B] Integration tests against real DB/Qdrant/OpenAI

## Security
- [x] API surface gated by shared key (M0); destructive reset double-gated
- [x] Rate limiting on LLM/upload endpoints
- [x] Upload size cap (bounded reads)
- [x] Security headers + request id
- [x] Critical npm advisory cleared (Next 14.2.33)
- [x] No secrets in client bundle (only `NEXT_PUBLIC_*`)
- [B] Real authn/authz + multi-tenant isolation (RLS) — M1
- [B] Audit log, UK data residency, DSAR/erasure — M5

## UX / UI
- [x] Responsive on mobile/tablet/desktop
- [x] Designed empty / loading / error states everywhere
- [x] Accessible dialogs (focus trap, aria, Esc, restore)
- [x] Skip link, focus-visible rings, reduced-motion support
- [x] Consistent labels, icons, button styles, brand tokens
- [x] Real settings hub (no "demo" copy)
- [~] Full WCAG AA audit (axe) — spot-checked; formal pass recommended
- [B] Onboarding wizard + sample-data loader — M3-T09

## Performance
- [x] React Query caching/dedup (no refetch storms)
- [x] Skeletons prevent layout shift
- [x] Singleton external clients (backend)
- [B] Redis cache + async ingestion (needs Redis)

## Observability & ops
- [x] Structured logging + request ids
- [ ] Sentry/error reporting wired (hook point added in `ErrorBoundary`)
- [ ] Health/uptime monitoring + staging env + rollback plan
- [x] `.env.example` documents new vars (see RELEASE_NOTES)

## Docs
- [x] `PROJECT_REVIEW.md`, `IMPLEMENTATION_PLAN.md`
- [x] `QA_TODO.md`, `BUG_REPORT.md`, `RELEASE_NOTES.md`, `RELEASE_CHECKLIST.md`
- [x] New env vars + breaking changes documented

## Go / No-go
- **Internal/staging demo:** ✅ Go — stable, secured behind an API key, fully responsive.
- **Public paid launch:** ⛔ No-go until **M1 (auth + multi-tenancy + RLS)**, billing (M4), and compliance baseline (M5) land. See `IMPLEMENTATION_PLAN.md` Launch Gate.
