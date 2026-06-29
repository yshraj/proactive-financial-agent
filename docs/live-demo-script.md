# KritiFin — Live Demo Script (5–10 minutes)

Use this script for hackathon judges, investor demos, or adviser walkthroughs. The app is pre-loaded with demo data (Alan & Lynne Partridge as top priority, ISA allowance story, overdue follow-ups).

## Before you start

1. Open `/login` → click **Enter demo workspace** (auth bypass when Supabase is not configured).
2. Confirm the simulated date in the header matches “today” for predictable alerts.
3. Optional: collapse browser bookmarks bar; use 1280×800 or projector resolution.

## Ideal walkthrough order (~8 minutes)

| Step | Screen | Time | Primary action |
|------|--------|------|----------------|
| 1 | Dashboard | 90s | Scan briefing + spotlight |
| 2 | Meeting Brief | 90s | Prepare brief (auto-generates) |
| 3 | AI Copilot | 90s | ISA allowance query (auto-ask via deep link) |
| 4 | Draft email | 60s | From dashboard or brief |
| 5 | Clients | 45s | Client 360 snapshot |
| 6 | Ingestion | 45s | Show upload → extract story |
| 7 | Close | 30s | Return to dashboard KPIs |

---

## Step 1 — Morning dashboard (90s)

**Navigate:** Already on `/dashboard` after login.

**What to show:**
- **Today's briefing** — AI morning digest loads expanded by default.
- **Top priority spotlight** — Alan & Lynne Partridge with one-click actions.
- **Priority timeline** — ranked list for the next 30 days.
- **KPI strip** — reviews due, follow-ups, compliance at a glance.

**Talking points:**
> "Every morning, KritiFin tells James what deserves attention — not a static CRM list, but a prioritised briefing grounded in his client book."
>
> "The spotlight surfaces the highest-priority household. One click to prepare for the meeting, ask Copilot, or draft a follow-up email."

**Primary click:** **Prepare brief** on the spotlight card (or hero CTA).

**Avoid:** Expanding "Show all alert cards" or "More insights" unless asked — keeps scroll short.

---

## Step 2 — Meeting brief (90s)

**Navigate:** Click **Prepare brief** → `/brief?clientId=…&auto=1`

**What to show:**
- Client auto-selected from deep link.
- Brief auto-generates (thinking steps → markdown brief).
- Source citations from fact-finds and meeting notes.
- **Regenerate** if you want a second pass.

**Talking points:**
> "Before every client meeting, advisers spend 20–30 minutes pulling files together. KritiFin generates an executive brief from ingested documents — talking points, open actions, and compliance flags — in seconds."
>
> "Every claim links back to source documents. This is RAG, not hallucination."

**Primary click:** Scroll through brief, then **Draft follow-up email** (optional).

**Pro tip:** Mention the trust footer — "prioritisation aid, verify before acting."

---

## Step 3 — AI Copilot (90s)

**Navigate:** Sidebar **AI Copilot**, or dashboard **Ask AI Copilot** (deep link with query).

**What to show:**
- Pre-filled query: *"Show me everyone with ISA allowance still available this tax year"*
- Answer with client names and cited sources.
- Follow-up suggestion chips.

**Talking points:**
> "Advisers can't query their entire book in a CRM. Copilot answers natural-language questions across all clients, alerts, and ingested documents."
>
> "This ISA question surfaces cross-sell opportunities in seconds — work that would take an paraplanner half a day."

**Primary click:** Submit (or let auto-ask run), then click a follow-up chip.

**Alternate demo query (client-scoped):** From spotlight, **Ask Copilot** scopes to one household.

---

## Step 4 — Draft email (60s)

**Navigate:** Dashboard → **Draft email** on spotlight or timeline row.

**What to show:**
- Modal opens with AI-drafted subject and body.
- Context from the alert (review due, follow-up overdue).
- **Mark as done** closes loop on the alert.

**Talking points:**
> "KritiFin doesn't just flag priorities — it drafts the next action. Review, send, mark done. The completed list tracks adviser accountability."

---

## Step 5 — Client 360 (45s)

**Navigate:** Sidebar **Clients** → click **Alan & Lynne Partridge**.

**What to show:**
- Profile snapshot: assets, risk, last review.
- Open alerts and document list.
- Link to brief or Copilot from detail page.

**Talking points:**
> "Every client has a single view — profile, alerts, documents, and AI tools in one place. No tab-hopping across systems."

---

## Step 6 — Document ingestion (45s)

**Navigate:** Sidebar **Ingestion**.

**What to show:**
- Drag-and-drop upload zone.
- Previously ingested documents table.
- Explain: PDF/Word → extract clients, dates, follow-ups → vector index for RAG.

**Talking points:**
> "The magic starts with upload. Drop a fact-find or meeting note — KritiFin extracts structured alerts and indexes content for Copilot and briefs."
>
> "Duplicate detection prevents re-processing the same file."

**Do not:** Upload a large file live unless network is reliable; describe the flow instead.

---

## Step 7 — Close (30s)

**Navigate:** Back to **Dashboard**.

**Talking points:**
> "KritiFin is proactive, not reactive. Upload once, prioritise daily, prepare in one click, query the book in plain English, and act with drafted emails — all in under ten minutes of adviser time saved per day."

---

## Deep links for rehearsed demos

| Action | URL pattern |
|--------|-------------|
| Prepare brief (auto) | `/brief?clientId={id}&auto=1` |
| Copilot with query | `/chat?q={encoded}&clientId={id}` |
| Dashboard spotlight | `/dashboard` (top alert drives CTAs) |

Client IDs are dynamic — use dashboard spotlight buttons rather than hardcoding IDs.

## Demo constants (code)

See `frontend/lib/demo.ts`:
- `DEMO_COPILOT_QUERY` — ISA allowance question
- `DEMO_CLIENT_QUERY` — client-scoped action items
- `chatWithQuery()` / `briefForClient()` — deep link helpers

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Digest empty | Click **Refresh** on briefing card |
| Brief slow | Ensure mock server / backend is running; mention "thinking steps" |
| Copilot no sources | Normal for book-wide queries with sparse index — ISA query has sources in demo data |
| Auth wall | Use **Enter demo workspace** on login |

---

## Remaining polish opportunities

- **Voice-over mode:** Optional presenter notes overlay (not implemented).
- **Demo date preset:** One-click "Demo day" in date simulator.
- **Brief PDF export:** Already available via Download — practice once before live demo.
- **Mobile layout:** Responsive works; prefer desktop for projector.
- **Safari/Firefox:** Chromium is most reliable for live demos (some E2E gaps on WebKit/Firefox).
