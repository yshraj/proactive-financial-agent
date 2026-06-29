# AI Prompt & RAG Improvements

**Date:** June 2026  
**Prompt version hash:** computed at runtime as `PROMPT_VERSION` in `backend/app/services/prompts.py`  
**Scope:** All LLM call sites, RAG retrieval, caching, and hallucination controls.

---

## Summary

Centralised all adviser-facing prompts into `prompts.py`, extracted RAG logic into `rag_context.py`, unified LLM calls through `llm.complete_with_system()` with **temperature=0**, and versioned cache keys so prompt changes auto-invalidate stale responses.

---

## 1. Prompt improvements (by feature)

### Shared persona (`JARVIS_PERSONA`)

| Before | After |
|--------|-------|
| Inconsistent voice ("Jarvis", "proactive assistant", "financial adviser's assistant") | Single UK IFA copilot persona across all features |
| No explicit hallucination guard | "Use only facts in context — never invent clients, amounts, or dates" |
| Mixed US/UK terms | UK English: adviser, ISA, fact-find, Consumer Duty |

### Ask Jarvis (`CHAT_SYSTEM`)

| Before | After |
|--------|-------|
| Long unstructured system prompt listing all data fields | Two-block model: structured records vs numbered document excerpts |
| Soft "cite when possible" | **Mandatory `[n]` citations** for document claims; no citation for SQL-sourced facts |
| No length guidance | Cap at ~250 words unless listing many clients |
| 1024 max output tokens | 900 max (sufficient for concise answers) |

### Pre-meeting brief (`BRIEF_SYSTEM`)

| Before | After |
|--------|-------|
| Generic "one page" instruction | Fixed markdown sections: Snapshot → Priorities → From documents → Suggested agenda |
| Hardcoded RAG query `"{name} meeting notes fact find"` | Dynamic query from client name + open alert titles |
| 1024 max tokens | 1400 max (room for structured brief + talking points delimiter) |

### Client 360 summary (`CLIENT_SUMMARY_SYSTEM`)

| Before | After |
|--------|-------|
| User-only prompt, no system message | System + user template; exactly 2–3 sentences enforced |
| 256 max tokens | 220 max |

### Morning digest (`DIGEST_SYSTEM`)

| Before | After |
|--------|-------|
| User-only, duplicated persona | Shared `JARVIS_PERSONA` via system message |
| Verbose KPI labels in user context | Compact snapshot format |
| 320 max tokens | 280 max |

### Email drafts (`DRAFT_*_SYSTEM`)

| Before | After |
|--------|-------|
| User-only prompts | System + user templates |
| Default model `gpt-4o` (expensive) | `resolve_model("draft")` → `gpt-4o-mini` by default |
| Brief context truncated to 4000 chars | 3000 chars (sufficient for follow-up; saves input tokens) |
| 512 max tokens | 450 max |

### Document extraction (`EXTRACTION_SYSTEM`)

| Before | After |
|--------|-------|
| ~30-line prompt with many duplicated examples | ~20 lines; same schema and rules, fewer examples |
| 120k char document input | 100k char cap (~17% input reduction on large PDFs) |
| No temperature set | `temperature=0` for deterministic JSON |
| Separate prompt hash for cache | Uses global `PROMPT_VERSION` |

---

## 2. RAG & retrieval improvements

| Area | Before | After |
|------|--------|-------|
| **Score filtering** | None — always top-k even if irrelevant | Min cosine score 0.32 (`RAG_MIN_SCORE` env override) |
| **Chat chunks** | 6 hits × 1800 chars | 5 hits × 1200 chars |
| **Brief chunks** | 10 hits × 1500 chars | 8 hits × 1200 chars |
| **Brief query** | Static string | `brief_retrieval_query()` from name + alert titles |
| **Context format** | Mixed labels | Numbered `[n]` with client, doc type, date, relevance score |
| **Source preview** | 300 chars | 280 chars + `ref` index for citation linking |
| **Parallel fetch** | Chat: embed + DB parallel; RAG sequential after | Chat: structured + RAG fully parallel on cache miss |

### Structured context (token savings)

| Area | Before | After |
|------|--------|-------|
| Book client list | 50 clients, verbose fields | 30 clients, compact pipe format |
| Review overdue list | 50 names | 20 names |
| Alerts window | 30 rows with long descriptions | 20 rows, title-focused |
| Follow-ups | Description up to 120 chars | Title + due date only |
| Alert rows (brief) | 15 with 120-char descriptions | 12 with 80-char descriptions |

---

## 3. Caching improvements

| Cache key | Before | After |
|-----------|--------|-------|
| Chat answer | `chat:{query_hash}:{scope}` | `chat:{PROMPT_VERSION}:{query_hash}:{scope}` |
| Brief | `brief:{client_id}` | `brief:{PROMPT_VERSION}:{client_id}` |
| Summary | `summary:{client_id}` | `summary:{PROMPT_VERSION}:{client_id}` |
| Digest | `digest:{date}:{pulse_hash}` | `digest:{PROMPT_VERSION}:{date}:{pulse_hash}` |
| Draft (alert) | `draft:{alert_id}` | `draft:{PROMPT_VERSION}:{alert_id}` |
| Draft (brief) | `draft:brief:{client}:{ctx_hash}` | `draft:{PROMPT_VERSION}:brief:{client}:{ctx_hash}` |
| Extract | `extract:{prompt_hash}:{content_hash}` | `extract:{PROMPT_VERSION}:{content_hash}` |

**Invalidation on ingest:** `invalidate_client_ai_caches(client_id)` clears brief, summary, chat, and digest caches when new documents are indexed.

**Invalidation on reset:** `invalidate_all_ai_caches()` replaces manual prefix list (also clears structured context via `chat:` prefix).

---

## 4. Determinism & hallucination prevention

1. **`temperature=0`** on all OpenAI completions (configurable via `LLM_TEMPERATURE` env).
2. **Explicit "Not in your records"** instruction when context is missing.
3. **Structured vs document separation** — model told which block to trust for which question types.
4. **Mandatory `[n]` citations** for document-derived claims in chat answers.
5. **RAG score threshold** — low-relevance chunks excluded from context.
6. **No regulated advice** disclaimer in persona (Consumer Duty aware framing).

---

## 5. Estimated token savings (per typical request)

| Feature | Input savings | Output savings | Model savings |
|---------|---------------|----------------|---------------|
| Chat | ~15–25% (fewer/shorter chunks + compact SQL context) | ~10% (900 vs 1024 cap) | — |
| Brief | ~10% (better retrieval, fewer junk chunks) | — | — |
| Draft emails | ~25% (3000 vs 4000 context) | ~12% (450 vs 512 cap) | **~90% cost** (gpt-4o → gpt-4o-mini default) |
| Extraction | ~17% on large docs (100k vs 120k) + ~30% shorter system prompt | — | — |
| Digest / summary | ~15% (compact input + lower caps) | ~10% | Uses brief model (mini) |

**Draft emails** are the largest cost win: moving from `gpt-4o` to `gpt-4o-mini` by default while keeping quality acceptable for templated correspondence.

---

## 6. Quality improvements (expected)

- **More consistent voice** across copilot, briefs, digests, and emails.
- **Better brief relevance** via alert-title-aware RAG queries.
- **Traceable chat answers** via `[n]` citations matching source panel indices.
- **Less hallucination** from score filtering, explicit grounding rules, and temperature=0.
- **Fresher responses after ingest** — caches bust when documents are uploaded.
- **Safer upgrades** — prompt edits bump `PROMPT_VERSION` and invalidate stale caches automatically.

---

## 7. Files changed

| File | Role |
|------|------|
| `backend/app/services/prompts.py` | **New** — all system prompts, user templates, `PROMPT_VERSION` |
| `backend/app/services/rag_context.py` | **New** — search, score filter, citation formatting |
| `backend/app/services/llm.py` | temperature=0, `complete_with_system`, draft model tier |
| `backend/app/services/cache.py` | `invalidate_client_ai_caches`, `invalidate_all_ai_caches` |
| `backend/app/services/llm_extractor.py` | Import shared extraction prompt |
| `backend/app/routers/chat.py` | Full rewrite to use shared modules |
| `backend/app/routers/monitor.py` | Prompt templates + versioned cache keys |
| `backend/app/routers/ingest.py` | Cache invalidation on successful ingest |
| `backend/app/routers/settings.py` | Unified cache clear |
| `frontend/lib/types.ts` | Optional `ref` on `ChatSource` |

---

## 8. Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_TEMPERATURE` | `0` | Output determinism |
| `RAG_MIN_SCORE` | `0.32` | Minimum Qdrant cosine similarity |
| `DRAFT_LLM_MODEL` | (falls back to brief/LLM model) | Cheaper model for email drafts |
| `BRIEF_LLM_MODEL` | `gpt-4o-mini` | Briefs, digests, summaries |
| `LLM_MODEL` | `gpt-4o` | Chat copilot |

---

## 9. Remaining opportunities

- Inline `[n]` → source linking in frontend markdown renderer
- MMR / deduplication for overlapping chunks from same document
- Populate Qdrant `topics` field from extraction alert types
- Streaming responses for chat
- Redis-backed cache for multi-worker deployments
- Citation enforcement post-processing (validate `[n]` refs exist in sources)
