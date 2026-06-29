# AI-Powered CRM Competitive Analysis

**Product:** KritiFin (Proactive Financial Agent / Jarvis API)  
**Audience:** Engineering, product, and demo stakeholders  
**Last updated:** June 2026  
**Status:** Planning document — no implementation included

---

## Executive Summary

KritiFin is a proactive workspace for UK Independent Financial Advisers (IFAs). It ingests fact-finds and meeting notes, extracts structured client profiles and alerts, and surfaces AI-assisted prioritisation, Q&A, meeting briefs, and draft emails. The backend already implements hybrid RAG (Postgres + Qdrant), four distinct LLM use cases, and response caching.

Competitors in the adviser CRM space — Wealthbox, Redtail, Salesforce Financial Services Cloud, HubSpot Breeze, and Attio — differentiate less on raw AI capability and more on **workflow integration**. Their highest-rated features place AI at the moment of need: on the client record, before a meeting, and immediately after an interaction.

KritiFin's technical foundation is strong. The primary gap is **product packaging**: AI capabilities exist as separate pages rather than as an embedded client-relationship loop. Closing this gap requires minimal architectural change. Most recommended features reuse existing endpoints, prompts, and data models with small extensions or frontend-only wiring.

This document analyses the competitive landscape, evaluates proposed features against engineering criteria, and recommends five features for immediate implementation. Detailed sequencing and acceptance criteria live in [implementation-roadmap.md](./implementation-roadmap.md).

---

## Competitive Landscape

### Market context

Financial advisers operate under FCA and Consumer Duty pressure with large client books and heavy administrative load. Modern CRM platforms compete on:

1. **Meeting intelligence** — prep, transcription, summaries, follow-ups  
2. **Contextual AI** — answers grounded in client history, not generic chat  
3. **Proactive prioritisation** — what needs attention today and why  
4. **Compliance-friendly recordkeeping** — audit trails, email archiving, structured notes  

KritiFin's mock-data, upload-driven model is appropriate for demos and hackathons. It should not attempt full CRM parity (custodian sync, calendar integration, transcription pipelines) in the near term.

### Platform comparison

| Platform | Primary audience | Signature AI capabilities | Adviser-specific strengths |
|----------|------------------|---------------------------|----------------------------|
| **Wealthbox** | UK/US financial advisers | AI Notetaker, Meetings hub, AI Assistant, Agents & Playbooks (early access) | Native meeting prep/follow-up; adviser-first UX; activity feed |
| **Redtail CRM** | US advisers, Orion ecosystem | Finmate AI (transcription), Redtail Speak AI assistant | Deep Orion/eMoney/Riskalyze integration; per-database pricing |
| **Salesforce FSC / Agentforce** | Enterprise wealth managers | Einstein next-best-action, meeting prep agents, post-meeting follow-up, opportunity scoring | Compliance navigator, role-based agent templates, unified platform |
| **HubSpot Breeze** | General CRM (incl. financial services) | Breeze Assistant sidebar, meeting prep from calendar, cited follow-up drafts | CRM-grounded chat on every page; copy/send email workflow |
| **Attio** | Startups, flexible GTM teams | AI record summaries, Ask Attio NL query, enrichment, AI Attributes | Highly customisable data model; MCP integration |

### Patterns advisers consistently praise

1. **One-click meeting prep** — context assembled from CRM history without tab-switching  
2. **Post-meeting follow-up drafts** — emails referencing specific discussion points  
3. **Client record summaries** — relationship overview on opening a contact  
4. **Conversational CRM query** — "What open items does this client have?" with citations  
5. **Daily priority digest** — actionable summary at login, not a raw task list  

These patterns map directly to capabilities KritiFin already has in fragmented form.

---

## Current KritiFin Capabilities

### Product surface (frontend)

| Route | Page | Capability |
|-------|------|------------|
| `/dashboard` | Dashboard | Time-travel date picker; 30-day priorities; review-overdue; overdue follow-ups; KPIs; draft email; mark done |
| `/chat` | AI Copilot | Hybrid RAG Q&A; suggestion chips; source citations |
| `/brief` | Meeting Brief | Client selector; one-page brief; talking points; PDF export |
| `/alerts` | Alerts | Filterable alert table; draft email (no mark done) |
| `/admin` | Ingestion | PDF/DOCX upload; duplicate detection; document list |
| `/settings` | Settings | Clear all data; profile/workspace/export placeholders |

**Notable absence:** No client detail page, no client list route, no cross-page workflow deep links.

### Backend API (existing)

| Prefix | Endpoints | Purpose |
|--------|-----------|---------|
| `/api/monitor` | `GET /clients`, `/pulse`, `/alerts`, `/completed`; `PATCH /alerts/{id}/status`; `POST /draft-email` | Client list, dashboard data, alert lifecycle, LLM email drafts |
| `/api/chat` | `POST /`, `/brief` | Hybrid RAG chat; pre-meeting brief generation |
| `/api/ingest` | `GET /documents`, `POST /upload` | Document list; dual-path ingestion |
| `/api/settings` | `POST /clear-data` | Full data reset |

### AI and data infrastructure

| Component | Implementation |
|-----------|----------------|
| **LLM extraction** | GPT-4o (or Gemini) parses uploads → client profile + 2–8 alerts |
| **Hybrid RAG chat** | Structured Postgres context + Qdrant semantic search → synthesised answer |
| **Meeting brief** | Per-client structured data + client-filtered RAG → brief + talking points |
| **Draft email** | LLM draft from alert context; cached 30 min by `alert_id` |
| **Embeddings** | OpenAI `text-embedding-3-small` (1536-dim) in Qdrant `client_memory` |
| **Caching** | Brief 1 h, draft 30 min, chat 5 min, structured context 90 s, extraction 24 h |

### Partially built capabilities (not exposed in UI)

- **Client-scoped vector search** — `_search_qdrant(..., client_id=...)` exists in `chat.py` but `ChatRequest` has no `client_id` field  
- **Brief follow-up promise** — Meeting Brief `PageIntro` mentions "draftable follow-up" but no UI or API path delivers it  
- **Mark done on Alerts** — API supports `PATCH /alerts/{id}/status`; Dashboard has it; Alerts page does not  

---

## Gaps vs Competitors

| Competitor capability | KritiFin status | Gap severity |
|----------------------|-----------------|--------------|
| Client 360° record view | No client detail page | **High** — core CRM expectation |
| One-click meeting prep from priorities | Brief exists in isolation | **High** — workflow disconnect |
| Post-meeting follow-up email | Draft email alert-only | **Medium** — incomplete brief workflow |
| Client-scoped AI assistant | Book-wide copilot only | **High** — contextual AI is table stakes |
| Daily AI digest / next-best-action | Static KPI cards | **Medium** — demo polish gap |
| Meeting transcription | Not built | Low (defer — major integration) |
| Predictive scoring | Not built | Low (needs historical data) |
| CRM/custodian integrations | Out of scope | Low (explicit non-goal) |
| Multi-tenant data isolation | Schema has `adviser_id`; no RLS | Low for demo; high for production |

**Root cause:** KritiFin presents four AI tools as separate destinations. Competitors embed AI into a single client-relationship loop:

```
Upload → Client record → Prepare → Meet → Follow up → Mark done
```

---

## Feature Analysis

All candidate features were evaluated on seven criteria (1 = low, 5 = high; effort inverted where noted):

| Criterion | Definition |
|-----------|------------|
| **User impact** | How much the feature improves daily adviser workflow |
| **Dev effort** | Inverse score — 5 = easy, 1 = hard |
| **Backend reuse** | Leverage of existing APIs, services, and prompts |
| **Frontend effort** | Inverse score — 5 = mostly wiring, 1 = major new UI |
| **AI reuse** | Leverage of existing LLM pipelines vs new prompts/models |
| **Demo value** | Visual and narrative impact in a hackathon or investor demo |
| **Maintainability** | Long-term code simplicity and test surface |

### Scoring matrix

| # | Feature | User impact | Dev effort | Backend reuse | Frontend effort | AI reuse | Demo value | Maintainability | **Total** |
|---|---------|-------------|------------|---------------|-----------------|----------|------------|-----------------|-----------|
| F1 | Prepare-for-meeting deep links | 4 | 5 | 5 | 5 | 5 | 5 | 5 | **34** |
| F2 | Follow-up email from brief | 5 | 5 | 4 | 4 | 4 | 5 | 5 | **32** |
| F3 | Client 360° page + AI summary | 5 | 4 | 4 | 3 | 4 | 5 | 4 | **29** |
| F4 | Morning AI digest (dashboard) | 4 | 4 | 4 | 4 | 3 | 5 | 4 | **28** |
| F5 | Client-scoped AI Copilot | 5 | 3 | 3 | 3 | 4 | 4 | 4 | **26** |
| F6 | Mark done on Alerts page | 3 | 5 | 5 | 5 | 5 | 2 | 5 | **30** |
| F7 | Copy/mailto for draft emails | 3 | 5 | 5 | 5 | 5 | 3 | 5 | **31** |
| F8 | Global AI sidebar (AppLayout) | 4 | 2 | 3 | 2 | 4 | 4 | 3 | **22** |
| F9 | Client list / search page | 4 | 4 | 5 | 4 | 5 | 3 | 5 | **30** |
| F10 | Data export (CSV) | 3 | 4 | 5 | 4 | 5 | 2 | 5 | **28** |
| F11 | Edit extracted client data | 4 | 2 | 2 | 3 | 3 | 3 | 3 | **20** |
| F12 | Link documents to clients (FK) | 3 | 3 | 2 | 3 | 5 | 2 | 3 | **21** |
| F13 | Client dedup on ingest | 3 | 2 | 2 | 4 | 5 | 2 | 3 | **21** |
| F14 | Chat conversation history | 3 | 2 | 2 | 3 | 3 | 3 | 2 | **18** |
| F15 | Streaming chat responses | 2 | 1 | 1 | 2 | 3 | 3 | 2 | **14** |

*Note: F6 and F7 are high-value polish items but not selected for the top five because they do not advance AI CRM positioning. F7 is folded into F2 acceptance criteria.*

---

## Recommended Features (Top 5)

The five selected features maximise perceived product improvement while reusing existing backend infrastructure. All are Easy or Medium complexity with no schema migrations required (except optional document linking, which is deferred).

| Rank | Feature | Complexity | Est. time |
|------|---------|------------|-----------|
| 1 | Prepare-for-meeting deep links | Easy | 2–4 hours |
| 2 | Follow-up email from Meeting Brief | Easy | 3–5 hours |
| 3 | Client 360° page with AI summary | Easy–Medium | 4–6 hours |
| 4 | Morning AI digest on Dashboard | Medium | 6–8 hours |
| 5 | Client-scoped AI Copilot | Medium | 6–8 hours |

**Combined estimate:** 2–3 focused engineering days.

Detailed specs, acceptance criteria, and build order are in [implementation-roadmap.md](./implementation-roadmap.md).

---

## Technical Notes

### Stack constraints (unchanged)

- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind, TanStack Query, Framer Motion  
- **Backend:** FastAPI, PostgreSQL (Supabase), Qdrant, OpenAI/Gemini  
- **Auth:** Supabase JWT (optional); no tenant scoping in current queries  

### Reusable backend modules

| Module | Path | Reuse for |
|--------|------|-----------|
| Brief generator | `backend/app/routers/chat.py` → `_generate_brief()` | Client summary, digest context |
| Draft email | `backend/app/routers/monitor.py` → `POST /draft-email` | Brief follow-up extension |
| Structured context | `chat.py` → `_get_structured_context()` | Digest input, scoped chat |
| Qdrant filter | `chat.py` → `_search_qdrant(client_id=...)` | Client-scoped copilot |
| Pulse builder | `monitor.py` → pulse endpoint logic | Digest input |
| Cache layer | `backend/app/services/cache.py` | All new LLM endpoints |

### API extension patterns

New endpoints should follow existing conventions:

- Rate limiting via `@limiter.limit("30/minute")` on LLM routes  
- Pydantic request/response models  
- Cache keys with TTL from `cache.py`  
- No breaking changes to existing request shapes  

### Frontend extension patterns

- Add routes to `frontend/lib/routes.ts`  
- Add React Query hooks to `frontend/hooks/useApi.ts`  
- Reuse `AlertCard`, `DraftEmailModal`, `Card`, `PageIntro`, `EmptyState`  
- Deep links via `router.query` on existing pages  

---

## Estimated Complexity

| Tier | Definition | Features in tier |
|------|------------|------------------|
| **Easy** | Frontend-only or single-endpoint extension; no schema change; < 4 hours | F1, F6, F7 |
| **Easy–Medium** | One new read endpoint + new page; 4–6 hours | F3, F9 |
| **Medium** | New LLM endpoint or request-shape extension + multi-component UI; 6–8 hours | F2, F4, F5 |
| **Hard** | Schema migration, new service, or third-party integration; 2+ days | F11–F15, deferred items |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM latency on digest/brief follow-up | Medium | Demo stalls | Cache aggressively; use `gpt-4o-mini`; show skeleton UI |
| Duplicate clients on re-upload | Existing | Client 360° shows wrong data | Document as known limitation; defer dedup (F13) |
| Brief follow-up quality without meeting transcript | Medium | Generic emails | Pass talking points + open alerts as structured context |
| Client-scoped chat cache collisions | Low | Stale wrong-client answers | Include `client_id` in cache key |
| Scope creep into full CRM | Medium | Hackathon timeline slip | Strict defer list; no CRUD beyond read-only client page |
| Playwright test breakage from new routes | Medium | CI failure | Add `data-testid` on new components; update nav tests |

---

## Deferred Features

Features intentionally excluded from the current roadmap:

| Feature | Reason to defer |
|---------|-----------------|
| AI meeting transcription (Wealthbox Notetaker, Finmate) | Requires Zoom/Teams integration, audio storage, and compliance review — multi-week effort |
| Predictive lead/opportunity scoring (Salesforce Einstein) | No conversion history or pipeline data in mock mode |
| Web-based contact enrichment (Attio) | Different product surface; advisers expect data from fact-finds |
| Autonomous agents / playbooks (Wealthbox Agents, Agentforce) | Needs task engine, permissions, audit trail |
| CRM/custodian integrations (Intelliflo, Orion) | Explicitly out of scope for MVP |
| Multi-tenant RLS and adviser scoping | Production requirement; not needed for demo |
| Global AI sidebar in AppLayout | Higher UI complexity; client-scoped copilot delivers 80% of value |
| Streaming chat | No backend streaming today; marginal demo benefit |
| Client dedup on ingest | Schema/logic change; document as known limitation |
| Document–client FK | Useful but not blocking top five |
| Edit extracted data | Requires PATCH endpoints and validation — post-demo |
| Data export CSV | Settings placeholder; low AI CRM relevance |

---

## Future Ideas

Longer-term enhancements once the client-relationship loop is complete:

1. **Meetings entity** — Store generated briefs and follow-ups as meeting records (Wealthbox Meetings pattern)  
2. **Notification / morning email digest** — Scheduled job over pulse API  
3. **Command palette** — Cmd+K client search with NL prep ("Prep brief for Alan Partridge")  
4. **Household grouping** — Parse couples/families from `full_name` or extraction  
5. **Compliance audit log** — Track alert status changes and AI-generated content  
6. **Finmate-style transcription** — When calendar/video integration is available  
7. **Attio-style AI Attributes** — Custom computed fields on client records (e.g. "protection gap score")  

---

## Related documentation

- [high-impact-features-2026.md](./high-impact-features-2026.md) — **2026 competitive refresh**: 40+ prioritised high-impact features after the original Top 5 shipped  
- [implementation-roadmap.md](./implementation-roadmap.md) — Prioritised build plan and acceptance criteria  
- [FEATURES_AND_IMPLEMENTATION.md](../../FEATURES_AND_IMPLEMENTATION.md) — Current feature inventory  
- [README.md](../../README.md) — Product overview and setup  
