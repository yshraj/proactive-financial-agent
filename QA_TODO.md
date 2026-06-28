# QA TODO — Living Checklist

> Release-candidate QA tracker for Proactive Financial Agent (Jarvis).
> Status legend: `[ ]` open · `[x]` done · `[~]` partial/deferred · `[B]` blocked (needs external service)
> Cross-refs: [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md), [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), [`BUG_REPORT.md`](BUG_REPORT.md).

## Session scope decision
- **In scope (fully implemented + Playwright-validated):** M3 UI/UX overhaul, frontend half of M2 (API client, types, hooks, error handling, states, a11y, responsive shell), e2e harness.
- **In scope (implemented + statically validated):** M0 backend security hardening + backend M2 cleanups (singletons, logging, dead refs).
- **Deferred / blocked this session (documented in RELEASE_NOTES):** M1 auth+tenancy+RLS, M4 Stripe billing, M5 audit/DSAR, M6 streaming/memory, M7 integrations — all require provisioning external services (Supabase/Stripe/CRM) and a live DB, which are unavailable in this environment. Validating untested auth across every route without a DB would risk regressions, so it is sequenced as the next run.

---

## Authentication & Security
- [B] Login / logout / session refresh (M1 — needs auth provider)
- [B] Protected routes / authorization / tenant isolation (M1)
- [x] API-key gate on backend routes (M0 stopgap)
- [x] Guard destructive `clear-data` endpoint
- [x] Upload size limit (reject oversized before full read)
- [x] Rate limiting on LLM/cost endpoints
- [x] No client-side secrets leaked (audit env usage)
- [x] Error responses don't leak internals/stack traces

## User onboarding
- [x] First-run empty state acts as onboarding (clear CTA, teaching copy)
- [x] Remove broken "seed script" reference
- [~] Guided multi-step onboarding flow (basic empty-state onboarding done; full wizard deferred to M3-T09)

## Navigation
- [x] Sidebar active state correct on every route
- [x] Mobile drawer nav opens/closes, traps focus, closes on route change
- [x] Logo/home link works
- [x] No dead links / 404s in nav

## Dashboard
- [x] Loading skeleton matches layout
- [x] Empty state when no data
- [x] Error state when API fails (recoverable)
- [x] KPIs render; no duplicate data presentations confusing the user
- [x] Draft-email + mark-done actions work

## Agent functionality (Ask Jarvis / Brief / Draft / Alerts)
- [x] Ask: submit valid query → answer + sources
- [x] Ask: empty/whitespace query handled
- [x] Ask: error state on API failure
- [x] Brief: generate → renders brief + talking points
- [x] Draft email modal: loads, copy, mark-done, close, focus trap
- [x] Alerts: filters work; labels human-readable (no raw enums)

## Forms
- [x] Ingestion: file type validation, invalid file rejected with message
- [x] Ingestion: progress reflects real states (no fake timers)
- [x] Select/date inputs accessible (labels, keyboard)

## Modals & dialogs
- [x] Focus trapped; Esc closes; backdrop click closes; focus restored
- [x] `role="dialog"` + `aria-modal` + labelled

## Settings
- [x] No "demo" copy
- [x] Destructive action requires explicit confirmation
- [x] Structured into a real settings layout

## API calls / Error handling / Network failures
- [x] Centralized API client with typed errors + timeouts
- [x] Graceful handling of 4xx/5xx/network down
- [x] No unhandled promise rejections in console

## Loading & empty states
- [x] Every async surface has a designed loading state
- [x] Every list/page has a designed empty state

## Responsive & mobile
- [x] 390px: every page usable (was critically broken)
- [x] 768px / 1024px / 1440px breakpoints sane
- [x] No horizontal overflow; tables scroll/stack

## Accessibility
- [x] Keyboard nav across interactive elements
- [x] Focus visible; focus management in modals/drawer
- [x] ARIA on dialogs, live region for chat answer
- [x] Color contrast AA on text/badges
- [x] Skip-to-content link

## Performance
- [x] No obvious unnecessary re-renders / refetch storms (React Query)
- [x] No layout shift on load (skeletons)
- [x] Bundle reasonable (icon tree-shaking, no heavy deps added)

## Visual consistency
- [x] Single design-token source (brand color, spacing, radius)
- [x] Consistent button casing/sizing
- [x] Consistent labels across pages
- [x] Icon set (no emoji in a compliance tool)

## Console errors / Browser compatibility
- [x] No console errors/warnings on any page (verified via Playwright)
- [x] Chromium verified via e2e; modern-evergreen assumptions documented

## Edge cases
- [x] Rapid navigation between pages
- [x] Refresh on every route
- [x] Back/forward navigation
- [x] Invalid inputs to forms
- [x] API returns empty arrays
- [x] API timeout / 500

## Regression testing
- [x] Final full e2e regression pass green
- [x] Previously fixed bugs re-verified

---
_This file is updated continuously as issues are found and fixed; see BUG_REPORT.md for details._
