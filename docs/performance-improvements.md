# KritiFin Performance Improvements

Production-level performance pass focused on rendering, API efficiency, caching, and bundle size — without changing functionality.

## Summary

| Area | Before | After |
|------|--------|-------|
| Dashboard DB queries | ~8 duplicate pulse queries (/pulse + /digest) | ~4 queries (60s pulse cache shared) |
| Digest LLM fetch | Always ran, even when collapsed; double-fetch on refresh | Gated when collapsed; single refresh via `refreshDigest()` |
| Auth token lookup | `getSession()` per parallel API call | In-memory token cache with auth listener |
| App shell animation | framer-motion JS on every route change | CSS `animate-fade-in` (60fps, no JS loop) |
| Draft email modal | Eagerly bundled on 4 pages | Dynamic import via `LazyDraftEmailModal` |
| Digest card | Eager import on dashboard | Dynamic import (code-split chunk) |
| Pulse grid DOM | All alerts rendered | Capped at 12 cards + link to full list |
| Alert cards | Re-rendered on every parent update | `React.memo` + stable `onDraftAlert` handler |
| Alerts filter UX | Full skeleton on refetch | `placeholderData` keeps table visible |
| PostgreSQL | New connection per query | `ThreadedConnectionPool` (2–20 connections) |
| Ingest alert inserts | N connections (one per alert) | Single `executemany` batch |
| Brief generation | 2 DB connections | 1 connection (merged queries) |
| Alert status update | 2 DB round-trips + partial cache bust | 1 query with JOIN + full AI cache invalidation |
| `_app` First Load JS | ~106 kB shared | ~106 kB shared (AppLayout kept static to avoid hydration issues) |

## Frontend Changes

### React Query (`hooks/useApi.ts`)
- Stable digest query key (removed `refresh` from key — fixes double-fetch)
- `useDigest()` returns `refreshDigest()` for explicit cache bypass
- `placeholderData` on alerts queries for smoother filter changes
- Extended `staleTime` / `gcTime` for stable data (`clients`, `documents`)
- `prefetchClients()` helper for nav hover warming

### Rendering
- `AlertCard`: `React.memo`, `draftAlertId` + `onDraftAlert` props
- `DigestCard`: `React.memo`, fetch gated until expanded
- `LayoutContext`: memoized provider value
- `dashboard.tsx`: `useMemo` for weekly chart and pulse slice

### Code splitting
- `LazyDraftEmailModal.tsx` — dynamic import, rendered only when open
- `DigestCard` — dynamic import on dashboard
- `react-markdown` — already split (chat, brief)

### API client (`lib/api.ts`)
- Cached Supabase access token with `onAuthStateChange` listener
- Avoids redundant `getSession()` on parallel dashboard requests

### Navigation
- Client list prefetch on hover for Clients / Copilot / Meeting Brief links

### Animations
- Removed `framer-motion` from `AppLayout` (landing/auth still use it)
- Route transitions use CSS only — compositor-friendly, respects reduced-motion CSS

## Backend Changes

### Connection pooling (`app/db.py`)
- `ThreadedConnectionPool` with min 2 / max 20 connections
- Automatic rollback on read paths before returning to pool

### Pulse cache (`app/services/cache.py`, `app/routers/monitor.py`)
- `PULSE_TTL = 60s` — shared by `/pulse` and `/digest`
- Digest refresh bypasses pulse cache via `invalidate_pulse_caches()`

### Cache invalidation
- Alert status changes now call `invalidate_client_ai_caches(client_id)`
- Pulse cache cleared on ingest, alert updates, and full data reset

### Query consolidation
- `_generate_brief`: single cursor for client + alerts
- `update_alert_status`: JOIN clients for name in one query
- Ingest: batch alert inserts with row-by-row fallback

## Files Changed

### Frontend
- `pages/_app.tsx` — React Query `gcTime`
- `pages/dashboard.tsx` — memoization, pulse cap, lazy modal/digest
- `pages/alerts.tsx`, `pages/brief.tsx`, `pages/clients/[id].tsx` — lazy modal
- `hooks/useApi.ts` — digest fix, prefetch, placeholderData, gcTime
- `lib/api.ts` — auth token cache
- `contexts/LayoutContext.tsx` — memoized value
- `components/AppLayout.tsx` — CSS animation, nav prefetch, removed framer-motion
- `components/AlertCard.tsx` — memo + stable draft props
- `components/DigestCard.tsx` — memo, gated fetch, fixed refresh
- `components/LazyDraftEmailModal.tsx` — new dynamic wrapper

### Backend
- `app/db.py` — connection pool
- `app/services/cache.py` — pulse cache, invalidation helpers
- `app/routers/monitor.py` — pulse cache, digest ordering, alert status JOIN
- `app/routers/chat.py` — merged brief DB queries
- `app/routers/ingest.py` — batch alert inserts

## Remaining Optimization Opportunities

| Priority | Opportunity | Notes |
|----------|-------------|-------|
| P1 | Redis cache for multi-worker deployments | In-memory cache is per-process |
| P1 | List virtualization | `@tanstack/react-virtual` when books exceed ~50 rows |
| P2 | In-flight LLM deduplication | Prevent double-click generating duplicate briefs |
| P2 | Embedding cache | Key by query hash in `rag_context.py` |
| P2 | Composite DB indexes | `alerts(status, trigger_date)`, `alerts(client_id, status)` |
| P2 | Dynamic AppLayout in `_app` | Requires SSR-safe loading strategy to avoid hydration mismatch |
| P3 | Landing page framer-motion → CSS | Further reduce marketing bundle |
| P3 | `@next/bundle-analyzer` in CI | Track bundle regressions |
| P3 | Server pagination for alerts/clients | When datasets grow beyond demo scale |
| P3 | Lighthouse CI in pipeline | Automated performance budgets |

## Verification

- `npm run build` — passes
- `npm run test:e2e -- --project=chromium` — 17 passed, 1 skipped
- No functionality changes; UI behaviour preserved
