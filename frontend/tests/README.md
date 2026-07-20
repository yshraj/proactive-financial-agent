# Playwright E2E Tests

This directory contains the KritiFin end-to-end test framework.

## Structure

- `auth.setup.ts` logs in once and writes reusable storage state to `tests/.auth/user.json`.
- `fixtures/base.ts` exposes Page Object Models and fails tests on unexpected console errors.
- `pages/` contains Page Object Models.
- `helpers/` contains reusable API, console, screenshot, and network fault-injection helpers.
  - `helpers/network.ts` mirrors the backend's structured 429 (`{error, limit_type, reset_at, detail}` + `Retry-After`/`X-RateLimit-*`) and provides deterministic delay/failure injection.
- `test-data/` contains shared upload payloads (`files.ts`) and edge-case prompts (`prompts.ts`).
- `mock-server.mjs` is a self-contained FastAPI-compatible mock for local frontend tests (stateful: async upload jobs and per-conversation chat history).

## Suites

| Spec | Covers |
| --- | --- |
| `auth.spec.ts` | Demo + credentialed sign-in, signup/forgot/reset pages, open-redirect guard, session persistence and expiry |
| `app-journey.spec.ts`, `qa-adviser-journey.spec.ts` | Core adviser happy paths across every page |
| `ai-copilot.spec.ts` | Conversation threading, markdown/citations, loading lock, restore after reload, multi-tab, draft-email regenerate/copy |
| `credits.spec.ts` | Lifetime balance visibility, variable costs, pre-action confirmation, backend hard stops, manual requests, and history |
| `usage-limits.spec.ts` | Temporary per-minute abuse protection (429), distinct from lifetime credits |
| `edge-cases.spec.ts` | Unicode/emoji/RTL/special chars, very long prompts, double submit, rapid clicks, oversized/multi-file uploads, refresh persistence |
| `settings-data.spec.ts` | Clear-data confirmation flow (route-mocked — never mutates a real backend), first-run onboarding, audit approval, posture |
| `network.spec.ts` | Offline mode, slow responses, request/response contracts, retry semantics |
| `resilience.spec.ts` | 404s, 5xx recovery, upload validation, ingestion pipeline UX |
| `accessibility.spec.ts` | axe WCAG scans, keyboard navigation, focus management, live regions |
| `responsive.spec.ts` | Desktop/tablet/mobile navigation (device projects) |
| `performance.spec.ts` | Load/transition/answer budgets + lazy-chunk check (Chromium desktop only) |
| `api.spec.ts` | Backend API contract smoke tests |

## Local Runs

```bash
npm run test:e2e
npm run test:e2e:ui
npm run test:e2e:headed
npm run test:e2e:debug
```

By default, Playwright reads `.env.test`, starts the mock backend, starts Next.js, and runs tests against `http://localhost:3000`.

## Deployed Environment Runs

Set these environment variables in `.env.test` or CI:

```bash
PLAYWRIGHT_BASE_URL=https://your-deployed-frontend.example.com
PLAYWRIGHT_API_URL=https://your-deployed-backend.example.com
E2E_SKIP_WEBSERVER=true
E2E_EMAIL=adviser@example.com
E2E_PASSWORD=your-test-password
```

When Supabase auth is not configured, tests use the local **Enter demo workspace** flow. When auth is configured, `E2E_EMAIL` and `E2E_PASSWORD` are required.

## Artifacts

- HTML report: `playwright-report/`
- JUnit XML (for CI test panels): `playwright-results/junit.xml`
- Failure artifacts (trace, video, screenshot): `test-results/`
- Successful major-page screenshots are attached to each test's output directory.

## Isolated local runs

If your real dev stack is already running on ports 3000/8000, run the suite on
its own ports so Playwright starts a fresh Next.js + mock backend pair instead
of reusing (and testing against) your live servers:

```bash
PLAYWRIGHT_BASE_URL=http://localhost:3100 PLAYWRIGHT_API_URL=http://localhost:8100 npm run test:e2e
```
