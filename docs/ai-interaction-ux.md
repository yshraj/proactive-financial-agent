# KritiFin AI Interaction UX Improvements

UX pass to make every AI surface feel intelligent, contextual, trustworthy, and delightful — without changing underlying models.

## Summary of Changes

### New shared AI component library (`frontend/components/ai/`)

| Component | Purpose |
|-----------|---------|
| `AiMarkdown` | Consistent markdown with citation badge links, table styling, blockquotes |
| `AiSourceList` | Numbered expandable sources with relevance confidence badges |
| `AiThinkingCard` | Staged loading steps (simulates progress without streaming) |
| `AiTrustFooter` | AI-generated badge, timestamp, source count, compliance disclaimer |
| `AiBadge` | Compact trust indicator pill |

### Utilities (`frontend/lib/ai.ts`)

- `linkifyCitations()` — converts `[1]` to scrollable anchor links
- `relevanceLabel()` / `relevanceBadgeClass()` — High/Medium/Low match indicators
- `aiErrorMessage()` — contextual, recovery-oriented error messages
- `getFollowUpSuggestions()` — dynamic follow-up prompts after each answer
- `scrollToSource()` — citation click → highlight source card

---

## Touchpoint Improvements

### AI Copilot (`pages/chat.tsx`)

**Before:** Single-shot answer hidden during loading; sources in plain accordion; no empty state; generic errors.

**After:**
- Conversation thread (question bubbles + answer cards persist)
- Empty state with primary CTA to try first suggestion
- Staged loading card with rotating progress steps
- Inline citation badges `[1]` linked to numbered source cards
- Relevance confidence on each source (High/Medium/Low match)
- Contextual follow-up suggestions after each answer
- Trust footer on every answer
- Improved error messages with recovery hints

### Meeting Brief (`pages/brief.tsx`)

**Before:** Decorative placeholder tiles; no sources; basic skeleton loading.

**After:**
- Staged loading with brief-specific progress steps
- Removed misleading placeholder tiles
- Document sources exposed from backend RAG
- Regenerate button
- Numbered talking points with visual hierarchy
- Trust footer + AI badge
- Empty state with direct generate CTA

### Morning Digest (`components/DigestCard.tsx`)

**Before:** Plain text paragraph; no provenance; basic skeleton.

**After:**
- Markdown rendering for formatted output
- Staged compact loading steps
- `generated_at` timestamp in trust footer
- AI badge on header
- Context-specific disclaimer

### Draft Email (`components/DraftEmailModal.tsx`)

**Before:** Subject hidden (mailto only); plain skeleton; generic errors.

**After:**
- Subject line displayed prominently
- Staged drafting progress steps
- Regenerate button
- Copy includes subject line
- Trust disclaimer for client communications

### Client 360 Summary (`pages/clients/[id].tsx`)

**Before:** Plain summary with no trust signals.

**After:**
- AI-generated badge
- Provenance note linking to Copilot and Meeting Brief for document-grounded detail

---

## Backend Changes

- `SourceOut.relevance` — exposes Qdrant match score to frontend
- `BriefResponse.sources` — returns RAG document sources with briefs
- Brief cache includes sources for consistent retrieval

---

## Files Changed

### Frontend (new)
- `components/ai/AiBadge.tsx`
- `components/ai/AiMarkdown.tsx`
- `components/ai/AiSourceList.tsx`
- `components/ai/AiThinkingCard.tsx`
- `components/ai/AiTrustFooter.tsx`
- `components/ai/index.ts`
- `lib/ai.ts`

### Frontend (modified)
- `pages/chat.tsx`
- `pages/brief.tsx`
- `pages/clients/[id].tsx`
- `components/DigestCard.tsx`
- `components/DraftEmailModal.tsx`
- `lib/markdown.ts`
- `lib/types.ts`
- `tests/mock-server.mjs`

### Backend (modified)
- `app/services/rag_context.py`
- `app/routers/chat.py`

---

## Remaining Opportunities

| Priority | Opportunity |
|----------|-------------|
| P1 | **Token streaming** — SSE endpoint + fetch reader for live answer typing |
| P1 | **Multi-turn context** — pass conversation history to backend for true follow-ups |
| P2 | **Brief cache bust on regenerate** — `refresh=true` param to force new brief |
| P2 | **Client summary refresh** — regenerate button + optional RAG grounding |
| P2 | **remark-gfm plugin** — native GFM table/list parsing in markdown |
| P3 | **Citation hover previews** — tooltip with source excerpt on citation hover |
| P3 | **Confidence on chat answers** — aggregate source relevance into answer-level indicator |
| P3 | **Suggested prompts on brief page** — quick-start templates per client type |

---

## Verification

- `npm run build` — passes
- `npm run test:e2e -- --project=chromium` — 17 passed, 1 skipped
