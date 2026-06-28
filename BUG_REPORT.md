# Bug Report & Resolutions

> Issues discovered during the release-candidate QA pass and how each was resolved.
> Validation was performed with TypeScript (`tsc --noEmit`), ESLint, a Playwright
> e2e suite (34 tests across desktop + mobile, see `frontend/e2e/`), and a backend
> security unit check. Cross-refs: [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md), [`QA_TODO.md`](QA_TODO.md).

Severity: 🔴 critical · 🟠 high · 🟡 medium · 🔵 low/quality

---

## 🔴 BUG-01 — Application unusable on mobile
- **Description:** On viewports < `md`, the fixed 240px sidebar never collapsed, crushing all content into an unreadable sliver on every page.
- **Root cause:** `AppLayout` rendered a `w-60 flex-shrink-0` sidebar with no responsive behaviour and no mobile navigation.
- **Resolution:** Rebuilt `AppLayout` with a desktop sidebar (`hidden md:flex`), a mobile top bar with a hamburger, and an accessible slide-in drawer (Esc to close, closes on route change, backdrop click). Added a skip-to-content link and account chrome.
- **Files:** `frontend/components/AppLayout.tsx`
- **Validation:** Playwright `mobile` project (Pixel 5) navigates every section via the drawer; `after-*-mobile.png` screenshots confirm full-width, readable layouts.

## 🔴 BUG-02 — Every API endpoint was unauthenticated (incl. data wipe)
- **Description:** No auth anywhere; any caller could read all client data, and `POST /api/settings/clear-data` could wipe Postgres + Qdrant anonymously.
- **Root cause:** No identity/authorization layer; destructive endpoint had no guard.
- **Resolution (M0 stopgap):** Added a shared **API-key gate** (`X-API-Key`) as a FastAPI dependency on every `/api/*` router; the destructive reset now additionally requires `ALLOW_DATA_RESET=true` and logs a warning. (Full auth + multi-tenancy is sequenced as M1 — see RELEASE_NOTES "Deferred".)
- **Files:** `backend/app/security.py`, `backend/app/main.py`, `backend/app/routers/settings.py`
- **Validation:** `backend/tests/test_security.py` + inline runtime check: open when unset, 401 on missing/wrong key, 200 on correct; reset blocked unless explicitly enabled.

## 🟠 BUG-03 — Unbounded file upload (memory-exhaustion DoS)
- **Description:** `await file.read()` buffered the entire upload into memory with no size cap.
- **Root cause:** No size validation before reading.
- **Resolution:** Reject via `Content-Length` fast-path and read in bounded 1 MB chunks, aborting with `413` past `MAX_UPLOAD_BYTES` (default 20 MB). Client mirrors the 20 MB guard.
- **Files:** `backend/app/routers/ingest.py`, `frontend/pages/admin.tsx`
- **Validation:** Code review + e2e: unsupported/oversized files are rejected client-side with a message.

## 🟠 BUG-04 — No rate limiting on paid LLM endpoints (cost abuse)
- **Description:** `chat`, `brief`, `draft-email`, and `upload` called paid APIs with no throttle.
- **Root cause:** No limiter.
- **Resolution:** Added `slowapi` per-IP limiter (`30/minute`) on the LLM/upload endpoints; wired the handler in `main.py`.
- **Files:** `backend/app/security.py`, `backend/app/main.py`, `backend/app/routers/{chat,monitor,ingest}.py`, `backend/requirements.txt`
- **Validation:** Syntax/compile validated; limiter registered on app state.

## 🟠 BUG-12 — Known-vulnerable Next.js
- **Description:** `next@14.2.15` flagged with a critical advisory; `npm install` reported a critical vuln.
- **Resolution:** Upgraded to `next@14.2.33` (latest 14.x; the earlier critical is resolved) and applied non-breaking `npm audit fix`. Residual advisories require a breaking Next 16 upgrade and only affect App-Router/`next/image`/self-host features this Pages-Router app doesn't use — documented as accepted/deferred.
- **Files:** `frontend/package.json`, `frontend/package-lock.json`
- **Validation:** `npm audit` — critical cleared; 2 nested advisories remain (documented).

## 🟡 BUG-05 — Raw enum labels leaked to users; inconsistent across pages
- **Description:** Alerts page showed `FOLLOW_UP` / `REVIEW_OVERDUE` verbatim while the Dashboard humanized them.
- **Root cause:** No shared label/format layer.
- **Resolution:** Central `lib/labels.ts` (label + badge maps) used by Dashboard, Alerts, AlertCard, and the Alerts filter options.
- **Files:** `frontend/lib/labels.ts`, `frontend/pages/{index,alerts}.tsx`, `frontend/components/AlertCard.tsx`
- **Validation:** e2e asserts humanized labels appear in the table and raw enums have count 0.

## 🟡 BUG-06 — Fake ingestion progress misled users
- **Description:** The "Uploading → Extracting → Indexing" steps advanced on `setTimeout(800/2200ms)`, unrelated to real backend progress.
- **Root cause:** Hard-coded timers decoupled from the request.
- **Resolution:** Replaced with an honest per-file status (processing → done / duplicate / error) reflecting the actual API result.
- **Files:** `frontend/pages/admin.tsx`
- **Validation:** e2e file-type rejection; manual review of status transitions.

## 🟡 BUG-07 — Settings page said "demo" and only offered a destructive button
- **Description:** Copy read "No in-app settings are needed for this demo"; the only control was "Clear all data".
- **Resolution:** Real settings hub (Account, Data & privacy) with placeholders for sign-in-gated features; removed all "demo" language.
- **Files:** `frontend/pages/settings.tsx`
- **Validation:** e2e asserts no "for this demo" text remains.

## 🟡 BUG-08 — No empty/loading/error states; technical error strings
- **Description:** Pages showed raw "Failed: 500" / "Monitor API not found" and no skeletons or empty states.
- **Root cause:** Hand-rolled fetch with minimal state handling.
- **Resolution:** React Query hooks + reusable `Skeleton`, `EmptyState`, `ErrorState` (with retry), and a toast system; designed states on every page.
- **Files:** `frontend/hooks/useApi.ts`, `frontend/components/ui/*`, all pages
- **Validation:** e2e smoke loads every page with zero console errors; states render with the mock backend.

## 🟡 BUG-09 — Dialogs not accessible
- **Description:** The email modal lacked focus trapping, `role="dialog"`/`aria-modal`, focus restoration, and Esc handling.
- **Resolution:** New `Modal` primitive: focus trap, `aria-modal`, labelled title, Esc + backdrop close, body scroll lock, focus restore. Reused by the draft-email and clear-data flows.
- **Files:** `frontend/components/ui/Modal.tsx`, `frontend/components/DraftEmailModal.tsx`, `frontend/pages/settings.tsx`
- **Validation:** e2e: modal opens, Esc closes; destructive confirm requires typing `DELETE`.

## 🟡 BUG-13 — Destructive reset had only a soft text confirm
- **Resolution:** Now requires typing `DELETE` (client) **and** `ALLOW_DATA_RESET=true` + API key (server).
- **Files:** `frontend/pages/settings.tsx`, `backend/app/routers/settings.py`, `backend/app/security.py`
- **Validation:** e2e: confirm button disabled until `DELETE` typed.

## 🔵 BUG-10 — Duplication & no data layer
- **Description:** `API_BASE`, `AlertRow`, and date formatters were copy-pasted across pages; each page hand-rolled loading/error state.
- **Resolution:** Shared typed API client (`lib/api.ts`), shared `lib/types.ts`, `lib/format.ts`, and React Query hooks (`hooks/useApi.ts`); added an app-level `ErrorBoundary`.
- **Files:** `frontend/lib/*`, `frontend/hooks/useApi.ts`, `frontend/components/ui/ErrorBoundary.tsx`, all pages
- **Validation:** `tsc --noEmit` + ESLint clean.

## 🔵 BUG-11 — Per-request external client instantiation
- **Description:** `OpenAI(...)` and `QdrantClient(...)` were constructed on every request.
- **Resolution:** Lazy process-singletons in `services/clients.py`, used by chat, brief, draft, extractor, and vector store. Removed the unused `sqlalchemy` dependency.
- **Files:** `backend/app/services/clients.py`, `backend/app/routers/{chat,monitor}.py`, `backend/app/services/{vector_store,llm_extractor}.py`, `backend/requirements.txt`
- **Validation:** Syntax/compile validated.

## 🔵 BUG-14 — Dead reference to a non-existent seed script
- **Description:** The dashboard empty state told users to "run the seed script" — no such script exists.
- **Resolution:** New empty state guides users to Ingestion with a CTA; removed the seed-script reference.
- **Files:** `frontend/pages/index.tsx`
- **Validation:** Visual review (`after-dashboard-*`).

## 🔵 BUG-15 — Demo-tier "backend waking up" toast
- **Description:** A global toast referencing the Render free-tier cold start leaked the demo narrative into the product.
- **Resolution:** Removed; per-query loading/error states now handle slow/failed requests gracefully.
- **Files:** `frontend/pages/_app.tsx`

## 🔵 Security headers missing
- **Resolution:** Added `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a per-request `X-Request-ID` via middleware.
- **Files:** `backend/app/main.py`

---

## QA-harness issues found & fixed during the cycles
These were defects in the **test code**, surfaced and fixed while iterating (evidence the suite is exercising real behaviour):

| ID | Issue | Fix |
|----|-------|-----|
| QA-01 | Playwright browser/arch mismatch under the sandbox cache | Run against the real `ms-playwright` cache; documented in RELEASE_NOTES. |
| QA-02 | `navigate` helper referenced `name` instead of `label` (ReferenceError) | Corrected the locator option. |
| QA-03 | Alerts label assertion matched a hidden `<option>` | Scoped the assertion to the table. |
| QA-04 | "Ask Jarvis" matched both the header CTA and nav link (strict-mode violation) | Scoped nav clicks to the `Primary` navigation landmark. |
| QA-05 | Mobile nav flake: drawer race when keyed on the menu button | Made the helper deterministic by keying on the nav landmark's visibility. Verified stable across repeated runs. |
