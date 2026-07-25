# Playwright E2E Tests

A minimal end-to-end suite focused on the critical user flows of KritiFin.

## Structure

- `auth.setup.ts` logs in once and writes reusable storage state to `tests/.auth/user.json`.
- `fixtures/base.ts` exposes Page Object Models and fails tests on unexpected console errors.
- `pages/` contains Page Object Models.
- `helpers/` contains the API-wait, console-error, credit-confirmation, and JSON route-mock helpers.
- `mock-server.mjs` is a self-contained FastAPI-compatible mock for local frontend tests (stateful: async upload jobs and per-conversation chat history).

## Suites

| Spec | Covers |
| --- | --- |
| `auth.spec.ts` | Landing page, demo + credentialed sign-in, open-redirect guard, session persistence |
| `app-journey.spec.ts` | The core adviser journey: dashboard, navigation across every page, prepare-for-meeting deep link, meeting brief + follow-up email, multi-turn copilot with reload persistence, client 360, alerts triage, document/transcript ingestion, settings, and API-failure recovery |
| `credits.spec.ts` | Balance visibility, confirmation before expensive actions, zero-credit hard stop with manual request |

Projects: `chromium` (desktop) and `mobile-chromium` (Pixel 5 emulation — exercises the drawer navigation path).

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

## Isolated local runs

If your real dev stack is already running on ports 3000/8000, run the suite on
its own ports so Playwright starts a fresh Next.js + mock backend pair instead
of reusing (and testing against) your live servers:

```bash
PLAYWRIGHT_BASE_URL=http://localhost:3100 PLAYWRIGHT_API_URL=http://localhost:8100 npm run test:e2e
```
