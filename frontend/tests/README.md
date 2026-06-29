# Playwright E2E Tests

This directory contains the KritiFin end-to-end test framework.

## Structure

- `auth.setup.ts` logs in once and writes reusable storage state to `tests/.auth/user.json`.
- `fixtures/base.ts` exposes Page Object Models and fails tests on unexpected console errors.
- `pages/` contains Page Object Models.
- `helpers/` contains reusable API, console, and screenshot helpers.
- `mock-server.mjs` is a self-contained FastAPI-compatible mock for local frontend tests.

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
- Failure artifacts: `test-results/`
- Successful major-page screenshots are attached to each test's output directory.
