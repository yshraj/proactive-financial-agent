# High-Impact Feature Backlog (2026 Competitive Refresh)

**Product:** KritiFin (Proactive Financial Agent)
**Audience:** Product, engineering, founders
**Last updated:** 29 June 2026
**Status:** Research + planning. No code changes in this deliverable.

**Companion docs:**
- [ai-crm-competitive-analysis.md](./ai-crm-competitive-analysis.md) — original landscape + the "Top 5 quick wins" (all now shipped)
- [implementation-roadmap.md](./implementation-roadmap.md) — build specs for those five features
- [../../FEATURES_AND_IMPLEMENTATION.md](../../FEATURES_AND_IMPLEMENTATION.md) — current shipped inventory

---

## Why this document exists

The earlier competitive analysis (June 2026) recommended five *small, demo-polish* features — prepare deep links, brief follow-up email, Client 360°, morning digest, scoped copilot. **All five are now built.** This document is the next horizon: a **large, prioritised set of high-impact features** grounded in fresh 2025-2026 research across three competitor clusters:

1. **AI meeting-intelligence tools** — Jump, Zocks, Finmate, Wealthbox AI, Fathom, Otter
2. **Horizontal AI CRMs** — Salesforce Agentforce/Einstein, HubSpot Breeze, Attio, Microsoft Copilot
3. **UK Consumer-Duty-native adviser AI** — AdvisoryAI, Aveni (FinLLM), Saturn, Recordsure, Intelliflo IQ, PlannerPal, Ammonite

The goal is *real impact*, not breadth for its own sake — but there are deliberately **many** features here, organised into themes so you can sequence them.

---

## What the market actually looks like in 2026

### The category exploded
AI for advisers did not exist as a budget line three years ago. By 2026, **Jump claims ~1 in 10 US advisers**; Jump + Zocks have raised **$170M+ combined**; **Morgan Stanley reports 98% advisor-team adoption** of its AI Debrief notetaker. In the UK, **AdvisoryAI** ranked #1 AI tool among advisers in H1 2025; **Saturn** raised a **$15M Series A** (Oct 2025, YC-backed) and **Aveni** raised **£12m** (June 2026) with **Lloyds + Nationwide** backing its purpose-built **FinLLM**. **Quilter signed Aveni for its entire adviser network** (Mar 2026).

### The "Great Bifurcation"
- **Agentic operating systems** (Jump, Zocks, Zeplyn, Mili) — moved past note-taking into orchestration that *acts* on the transcript.
- **CRM-native AI** (Wealthbox Oct 2025, Intelliflo IQ, Altruist Hazel) — AI embedded where the data already lives, often **bundled free** to undercut standalone vendors.
- **Generic tools** (Fathom, Otter, Granola) — where solo advisers start, but they lack the compliance/CRM/financial-data layer.
- **UK Consumer-Duty-native** (AdvisoryAI, Saturn, Aveni) — the suitability-report + FCA-evidence wedge.

### The killer workflow everyone is converging on
```
Capture meeting → structured notes + extracted DATA → update client record
   → draft follow-up email → create tasks → file compliance evidence
   (with a mandatory human-review gate before anything is filed/sent)
```
KritiFin already has fragments of this (briefs, draft emails, extraction-on-upload). The opportunity is to **own the whole loop** and add the **UK compliance layer** that US incumbents lack.

### Two strategic signals to act on
- **Almost no vendor discloses its LLM or data-residency.** Aveni (FinLLM, UK-hosted) and Zocks (no-recording) are the exceptions and they market it hard. **"UK data residency + we never train on your data + no audio retention" is a cheap, high-trust differentiator** KritiFin can adopt as a design principle today.
- **Regulatory headwind:** the **FCA is consulting on dropping the mandatory annual suitability-review requirement** (see CP26/10 below). Don't over-index features purely on "annual review letters"; frame around *ongoing-service evidence* and *Consumer Duty outcomes* instead, which are durable.

### Verified regulatory facts that change the roadmap

These come from FCA primary sources (handbook + 2025-2026 reviews/consultations) and are high-confidence. They directly determine what to build — and what *not* to.

- **Consumer Duty (PRIN 2A) is the design lens.** In force since 31 July 2023. Firms must keep **evidence of good outcomes**, **monitor outcomes on an ongoing basis** segmented by customer group (incl. vulnerable), and produce an **annual board report** (PRIN 2A.8/2A.9). The FCA's April 2026 review told firms to move past MI dashboards to genuine *analysis*. → drives features 11, 13, 14, 17b.
- **The mandatory 12-month review is likely going away.** FCA **CP26/10** ("Simplifying the pensions and investment advice rules", published 25 Mar 2026; **policy statement expected Q4 2026**) proposes replacing the rigid annual review with a **risk-based periodic frequency**. → **do not hard-code a 12-month rule**; build a configurable cadence engine (17a).
- **The COBS 16A.4 "10% portfolio depreciation" notification rule was permanently revoked, effective 23 Oct 2025.** → **do not build 10% depreciation alerting** as a compliance feature — it no longer exists.
- **ATR and capacity-for-loss must stay separate** (FG11/05) — don't bundle them with age/term into one score (17e).
- **MiFID II ex-post aggregated costs & charges (COBS 6.1ZA) is still required annually** (17d).
- **Fact-find data is often special-category data** (health → vulnerability/protection). UK GDPR needs an Article 6 basis **plus** an Article 9 condition and usually an "appropriate policy document" (DPA Sch 1). → handle carefully in 13 and 16.
- **The ROI bullseye:** advisers/paraplanners spend **~10-15 hrs/week on suitability reports** (~40% of the week), **4-6 hrs per report**, against a paraplanner shortage. → suitability drafting (10) is the clearest ROI target in the entire market.
- **Hallucination is the #1 adoption blocker** (error rates up to ~41% cited for finance queries; advisers demand source-referencing). **<5% of advisers have a full AI policy; 77% cite lack of a due-diligence framework.** → source-grounding + audit trail (14) + human review (12) are table stakes, not polish.

---

## How to read the feature tables

Each feature is tagged:

- **Impact** — adviser value + competitive necessity (★ to ★★★★★)
- **Effort** — for this stack (FastAPI + Postgres + Qdrant + OpenAI): **S** (days), **M** (1-3 wks), **L** (1-2 mo), **XL** (multi-month)
- **Reuse** — how much existing KritiFin code it leverages
- **Tag** — `[Table stakes]` (you lose without it) · `[Differentiator]` (genuine edge) · `[UK must-have]` (regulatory)
- **Integration?** — `Standalone` (buildable with uploads / in-app data, no third-party calendar/video/CRM) vs `Needs integration`

The strategic point from the research: **~80% of the rave-worthy value is buildable standalone** using uploaded audio / in-person capture / your own stored data. Only true *external* CRM field write-back and live calendar/video auto-join genuinely require third-party integrations — defer those.

---

## Theme 1 — Meeting Intelligence (the core loop)

This is the single highest-value theme in the entire market. KritiFin ingests documents today; it does not yet ingest *conversations*. Closing that gap is the biggest lever.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 1 | **Audio/transcript ingestion** — upload a recording or paste a transcript; Whisper → text → existing dual-path pipeline | ★★★★★ | M | Table stakes | Standalone |
| 2 | **Conversation → structured DATA extraction** — pull typed fields (assets, income, goals, risk attitude, dependents, life events), not just prose | ★★★★★ | M | Differentiator | Standalone |
| 3 | **Adviser-specific note templates** — discovery / annual review / prospect / suitability summary formats | ★★★★ | S | Table stakes | Standalone |
| 4 | **Follow-up email grounded in the actual conversation** — cite specific points + agreed next steps (extends current draft-email) | ★★★★ | S | Table stakes | Standalone |
| 5 | **Action-item extraction → tasks/alerts** — create `FOLLOW_UP`/`DEADLINE` alerts from the meeting automatically | ★★★★ | M | Table stakes | Standalone |
| 6 | **In-person + file-upload capture** — record on device or upload a file (avoids needing Zoom/Teams APIs) | ★★★★ | M | Differentiator | Standalone |
| 7 | **Pre-meeting prep: "what you promised last time"** — surface open commitments + last-meeting recap (Jump's signature feature; extends Brief) | ★★★★ | S | Differentiator | Standalone |
| 8 | **No-recording / privacy-first mode** — process transcript, store structured data only, configurable retention (Zocks' moat) | ★★★ | S | Differentiator | Standalone |
| 9 | **Live calendar/video auto-join** — bot joins Zoom/Teams/Meet | ★★★ | L | Table stakes (later) | Needs integration |

**Why this theme first:** Every leading tool — Jump, Zocks, Finmate, Wealthbox, Saturn, Aveni, AdvisoryAI — is built on this loop. KritiFin's existing `llm_extractor.py` (doc → profile + alerts), `rag_context.py`, Qdrant chunking, and draft-email endpoint are **directly reusable** — a meeting transcript is just another document type feeding the same pipeline. Features 1-5 turn KritiFin from a document tool into a meeting-intelligence tool with mostly *additive* work.

**Build note:** Start with #1+#2 (upload transcript → structured extraction reusing `llm_extractor` with a new prompt + JSON schema / function-calling). #3-#5 are prompt + small endpoint work. #7 extends the existing Brief. Defer #9 until there's pull.

---

## Theme 2 — UK Compliance & Consumer Duty (the regulatory moat)

This is where a **focused UK adviser tool beats US incumbents** (Jump/Zocks/Wealthbox are Reg BI-oriented, not Consumer-Duty-native). It is also where Saturn, Aveni, and AdvisoryAI are racing. For UK advisers several of these are **non-negotiable**.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 10 | **AI suitability report drafting** — generate suitability/annual-review letters from client data + meeting, in firm tone, with citations to source | ★★★★★ | L | UK must-have / Differentiator | Standalone |
| 11 | **Consumer Duty four-outcome mapping** — tag AI outputs/interactions to the 4 outcomes; produce "regulator-ready" evidence | ★★★★★ | M | UK must-have | Standalone |
| 12 | **Mandatory human-review/approval gate** — adviser-as-editor before any AI output is filed/sent; track edits for audit | ★★★★★ | S | UK must-have | Standalone |
| 13 | **Vulnerable-customer detection** — flag vulnerability signals (FCA FG21-1) from conversation/notes with context + recommended action | ★★★★ | M | UK must-have / Differentiator | Standalone |
| 14 | **Immutable audit trail** — timestamped log of every AI output: prompt, context, sources, model, who approved, edits | ★★★★ | M | UK must-have | Standalone |
| 15 | **Compliance pre-check ("Colin" pattern)** — pass/partial/fail grade of a document against COBS / Consumer Duty before it leaves the desk | ★★★★ | M | Differentiator | Standalone |
| 16 | **UK data-residency + no-training posture** — UK-hosted inference, "we never train on your data," documented subprocessors, trust page | ★★★★ | M | UK must-have | Standalone |
| 17 | **Fact-find auto-population** — fill/refresh a structured fact-find from meetings + documents (Intelliflo IQ updates 190+ fields) | ★★★★ | M | Differentiator | Standalone |
| 17a | **Configurable risk-based review-cadence engine** — track review due-dates, contact attempts, declines/non-responses; produce an evidence pack proving the paid-for service was delivered. Default 12-month but make frequency justifiable (see CP26/10 below) | ★★★★★ | M | UK must-have | Standalone |
| 17b | **Consumer Duty board-report data engine** — aggregate outcome metrics segmented by customer group (incl. vulnerable), surface poor-outcome disparities, auto-assemble the annual PRIN 2A.8/2A.9 board report ("analysis, not dashboards") | ★★★★ | M | UK must-have | Standalone |
| 17c | **Annual-review pack auto-assembly** — one-click compile of updated valuations, cashflow refresh, performance-vs-objectives, fee statement + review letter (Dynamic Planner targets sub-5-second review reports) | ★★★★ | M | Differentiator | Standalone |
| 17d | **MiFID II ex-post costs & charges statement** — auto-produce the annual personalised aggregated costs & charges disclosure (COBS 6.1ZA) and reconcile ongoing fees against services delivered (ties to 17a) | ★★★ | M | UK must-have | Standalone |
| 17e | **ATR + capacity-for-loss workflow (kept separate)** — orchestrate attitude-to-risk and capacity-for-loss as distinct assessments per FG11/05; evidence capacity for loss via cashflow stress scenarios. Orchestrate over existing profilers, don't rebuild psychometrics | ★★★ | M | UK must-have | Standalone |

**Why this theme:** Suitability-report drafting alone is the headline ROI claim across the entire UK market — AdvisoryAI/Aveni/Saturn all cite **4-6 hours → ~20 minutes**. It reuses KritiFin's brief generator, RAG, and prompts. **Vulnerable-customer detection is held essentially only by Aveni** today — a genuine wedge. The human-review gate (#12) and audit trail (#14) are cheap to build and disproportionately build trust with compliance teams.

**Build note:** #12 + #14 should be built *as infrastructure underneath every AI feature*, not as standalone screens — every generation flows through an approval + audit record. Do these early so later features inherit them.

---

## Theme 3 — AI-Computed Fields & Domain Scores (the Attio pattern, applied to advice)

Attio's architectural insight: **AI as record fields and workflow steps, not a side chatbot.** Applied to financial advice, the *computed scores* don't exist well in horizontal CRMs — this is a defensible, differentiating layer.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 18 | **AI-attribute engine** — generic primitive: per-field AI (classify / summarise / prompt-complete / research) with value + provenance + refresh, cached in Postgres | ★★★★ | M | Differentiator | Standalone |
| 19 | **Protection-gap score** — coverage vs need from income/dependents/debt; the clearest "advice" computed field (FP Alpha does this for insurance) | ★★★★★ | M | Differentiator | Standalone |
| 20 | **At-risk / churn score** — engagement decay + sentiment + life events → who's about to leave | ★★★★ | M | Differentiator | Standalone |
| 21 | **Planning-completeness score** — % of fact-find / advice areas covered; drives next-best-action | ★★★ | S | Differentiator | Standalone |
| 22 | **Relationship summary attribute** — auto-maintained 2-3 sentence client summary on every record | ★★★ | S | Table stakes | Standalone |

**Why this theme:** Build #18 well and #19-#22 become **configuration, not new systems** — a prompt template + record context → typed value with caching and provenance. KritiFin's Postgres (values + provenance) + existing cache layer map cleanly. **Protection-gap score (#19) is the single most "advice-shaped" differentiator** and a memorable demo artifact. Start LLM-reasoned-over-a-rubric; add calibrated ML later once data exists.

---

## Theme 4 — Proactive Engine (next-best-action & signals)

KritiFin is named the *Proactive* Financial Agent and already has a pulse/alerts engine. This theme makes the "proactive" claim real, matching Salesforce Einstein NBA / Attio agents / Wealthbox.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 23 | **Next-best-action engine** — per client: "review due," "fact-find stale," "protection gap," "referral-ready," ranked by LLM over the record | ★★★★ | M | Differentiator | Standalone |
| 24 | **Life-event & signal detection** — detect life events, sentiment shifts, contact-frequency decay from notes/transcripts → alerts | ★★★★ | M | Differentiator | Standalone |
| 25 | **Scheduled book digest** — cron-generated "clients needing attention this week," emailed/in-app (extends current daily digest) | ★★★ | S | Table stakes | Standalone |
| 26 | **Event-triggered playbooks** — multi-step task templates fired by events (meeting ended, review due, doc uploaded) — Wealthbox's strength | ★★★ | M | Table stakes | Standalone |

**Why this theme:** It builds directly on the existing pulse/alert model and the digest endpoint. NBA (#23) + signals (#24) pair naturally with the Theme-3 scores. Playbooks (#26) need a small event bus + trigger→action config in Postgres and become the substrate for agentic flows later.

---

## Theme 5 — Conversational & Agentic (depth on top of the copilot)

KritiFin has a working scoped copilot. The frontier is **memory** and **agents that act with approval**.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 27 | **Conversation memory / chat threads** — persistent multi-turn threads; each ask builds on the last (today each ask replaces the prior answer) | ★★★★ | M | Table stakes | Standalone |
| 28 | **Long-running per-client memory** — durable summarised profile + episodic recall of every meeting, used for prep and grounding | ★★★★ | M | Differentiator | Standalone |
| 29 | **Ask-with-citations over the whole book** — hybrid RAG (Qdrant) + tool-calling/text-to-SQL over Postgres for aggregates (AUM, counts), always cited | ★★★★ | M | Differentiator | Standalone |
| 30 | **Agentic workflows with human-in-the-loop** — chain research → draft agenda → draft email → create tasks, pausing at approval gates | ★★★★ | L | Differentiator | Standalone |
| 31 | **Web-research enrichment agent** — fill/refresh fields from web, grounded in record context (Attio's research agent), with provenance | ★★★ | M | Differentiator | Standalone (uses web tools) |

**Why this theme:** #27 is the most-felt UX gap today (single-shot chat). #29's hard part is *not hallucinating numbers* — always use tool-calling for any figure. #30 is the endgame; build it **last**, on top of the tools created by Themes 1-4, and route every client-facing action through the Theme-2 approval gate.

---

## Theme 6 — Document Intelligence (deepen the existing ingestion)

KritiFin already does doc → profile + alerts. The frontier players (FP Alpha, Holistiplan) turn documents into *planning gaps*.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 32 | **Per-doc-type extraction schemas** — tailored extraction for statements, tax docs, pension/transfer paperwork, insurance | ★★★★ | M | Differentiator | Standalone |
| 33 | **Document → planning-gap detection** — surface coverage/planning gaps from extracted data (FP Alpha model) | ★★★★ | L | Differentiator | Standalone |
| 34 | **Document ↔ client linking (FK)** — proper foreign key so Client 360° reliably shows each client's own documents | ★★★ | S | Table stakes | Standalone |
| 35 | **LOA / pack summarisation** — summarise letter-of-authority packs and long statements (Saturn/AdvisoryAI feature) | ★★★ | M | Differentiator | Standalone |

---

## Theme 7 — Platform & Foundation (the launch gate)

Not "features" in a demo sense, but the **IMPLEMENTATION_PLAN.md** M1 work is the gate before paying customers. Listed here so it isn't lost behind shinier items.

| # | Feature | Impact | Effort | Tag | Integration? |
|---|---------|--------|--------|-----|--------------|
| 36 | **Auth + multi-tenancy + RLS** — real accounts, `workspace_id` on all tables, Postgres RLS, scoped Qdrant + cache keys | ★★★★★ | XL | Table stakes (launch gate) | Needs integration |
| 37 | **Async ingestion + job status** — move ingestion off the request path; real progress (current progress bar is faked timers) | ★★★★ | L | Table stakes | Standalone |
| 38 | **Edit extracted client data** — `PATCH /clients/{id}` + edit UI to fix mis-extractions (protects demos and trust) | ★★★★ | M | Table stakes | Standalone |
| 39 | **Shared cache (Redis) + connection pool** — survive multi-worker; today in-memory cache cross-leaks across workers/tenants | ★★★ | M | Table stakes | Needs integration |
| 40 | **Data export (CSV)** + onboarding sample-data loader (current empty state references a non-existent seed script) | ★★★ | S | Table stakes | Standalone |

**Critical:** #36 (auth + multi-tenancy) is the single biggest gap before KritiFin can have customers — today all data is global. The in-memory cache (#39) will *cross-leak data between tenants* the moment multi-tenancy lands, so #39 is coupled to #36.

---

## The strategic wedge (if you do nothing else, do this)

The research points to one sharp, defensible position that neither US incumbents nor generic tools occupy:

> **A privacy-first, UK-Consumer-Duty-native meeting-and-document intelligence loop, with structured financial-data extraction and a human-review compliance gate.**

Concretely, the highest-leverage cluster is:

1. **Conversation → structured financial-data extraction** (#2) — Zocks' wedge, the #1 capability
2. **AI suitability report drafting** (#10) — the headline UK ROI (hours → minutes)
3. **Consumer Duty mapping + vulnerable-customer detection + human-review gate** (#11, #13, #12) — the UK compliance moat US tools lack
4. **UK data-residency / no-training / no-recording posture** (#16, #8) — cheap, high-trust, marketable today

This is exactly the combination AdvisoryAI, Saturn, and Aveni are racing to own — and KritiFin's existing extraction + RAG + brief + draft-email pipeline is ~60% of the plumbing already.

---

## Recommended build order

Each phase ends demoable; later phases reuse earlier infrastructure.

```
Phase A — Meeting loop foundation (Theme 1: #1-#5, #7)
    Turn KritiFin from a document tool into a meeting-intelligence tool.
    Reuses llm_extractor, rag_context, draft-email. Mostly additive.

Phase B — Compliance infrastructure (Theme 2: #12, #14 first; then #10, #11, #13, #16)
    Build the human-review gate + audit trail UNDER everything, then
    suitability drafting + Consumer Duty mapping + vulnerability detection.
    This is the UK moat and the headline ROI.

Phase C — Computed-field primitive + domain scores (Theme 3: #18 then #19-#22)
    Build the AI-attribute engine once; protection-gap + at-risk become config.

Phase D — Proactive engine (Theme 4: #23-#26)
    Make "proactive" real on top of pulse/alerts + the new scores.

Phase E — Memory + agents (Theme 5: #27, #28, #29, then #30)
    Chat threads + per-client memory; agentic flows LAST, routed through
    the Phase-B approval gate.

Parallel track — Foundation (Theme 7: #38, #40 now; #37, #39; #36 before launch)
    Quick wins (#38, #40) anytime. #36 auth/multi-tenancy is the launch gate.
```

**If you want a single next sprint:** Phase A #1+#2+#4 (upload transcript → structured extraction → grounded follow-up email) gives the most visible jump for the least new infrastructure, and it's the workflow 98% of Morgan Stanley advisers actually use.

---

## Risks & watch-items

| Risk | Note |
|------|------|
| **FCA may drop the annual suitability-review requirement** (CP26/10, policy statement expected Q4 2026) | Build a *configurable, risk-based* review-cadence engine (17a); don't hard-code 12 months. Frame around *ongoing-service evidence* + *Consumer Duty outcomes* |
| **Building a now-revoked rule** | The 10% portfolio-depreciation alert (COBS 16A.4) was revoked 23 Oct 2025 — do not build it |
| **Special-category data mishandling** | Fact-find/vulnerability data often includes health data; ensure UK GDPR Article 9 condition + appropriate policy document before processing it in #13/#16 |
| **Suitability reports are regulated documents** | All UK players ship draft + **mandatory human review** (#12). Never auto-file/auto-send regulated output. UK planners remain divided on AI suitability — lead with the human-in-the-loop framing |
| **LLM hallucinating figures in "Ask"** | Use tool-calling / text-to-SQL for any number; never let the LLM free-text aggregates |
| **In-memory cache cross-leaks tenants** | Couple Redis (#39) to the multi-tenancy work (#36) |
| **Data-residency claims must be true** | If you market UK hosting / no-training (#16), the infrastructure must actually back it — this is a due-diligence question buyers ask |
| **Scope creep** | The list is deliberately large; ship phase-by-phase, each demoable. Don't start agents (#30) before their tools (Phases A-D) exist |

---

## Competitor quick-reference (2026)

| Competitor | What they're known for | What KritiFin can learn / beat |
|-----------|------------------------|-------------------------------|
| **Jump** (jump.ai) | #1 US adviser notetaker; best CRM task-push; "what you promised last time" prep | Pre-meeting prep pattern (#7); agentic chaining (#30) |
| **Zocks** (zocks.io) | Structured DATA extraction + no-recording privacy; auto form-fill | The core wedge (#2, #8, #17) |
| **Finmate** (finmate.ai) | Near-100% transcription accuracy; in-person + file upload | Capture flexibility (#6) |
| **Wealthbox AI** | First CRM-native notetaker; Playbooks; bundled free | Native write-back + playbooks (#26) |
| **Fathom / Otter** | Cheap, fast, generic; no compliance/CRM/data layer | The gap KritiFin fills for advisers |
| **Salesforce Agentforce** | Atlas reasoning engine; event-triggered agents; Trust Layer PII masking | Agentic + audit/guardrails (#14, #30) |
| **HubSpot Breeze** | Prospecting agent; predictive lead scoring; Breeze Intelligence enrichment | Scoring (#20) + enrichment (#31) |
| **Attio** | AI Attributes as record fields; Ask Attio with citations; automations; MCP server | The computed-field primitive (#18); cited Ask (#29) |
| **AdvisoryAI** (UK, #1) | Three "AI employees" — capture / suitability draft / compliance check; 4-6h → 20min | The end-to-end UK loop (#2, #10, #15) |
| **Aveni** (UK) | FinLLM (Lloyds/Nationwide); 100% conversation QA; **vulnerable-customer detection**; Quilter deal | Vulnerability detection (#13); Consumer Duty evidence (#11) |
| **Saturn** (UK, YC, $15M) | Suitability drafting + meeting notes; Ateb compliance templates; human-in-loop | Suitability (#10) + human-review (#12) |
| **Recordsure** (UK, TCC) | 100% file/call review; Consumer Duty outcomes; ISO 27001 / Azure | Audit-grade review (#14, #15) |
| **Intelliflo IQ** (UK) | Native AI in dominant UK back-office; fact-find across 190+ fields; -85% admin | Fact-find auto-population (#17) |

---

## Sources

Research conducted June 2026 via web search across vendor sites and trade press (Kitces, Citywire New Model Adviser, Professional Adviser, WealthTech Today, XYPN, Financial Planning Today, tech.eu, Finextra).

- **Meeting tools:** jump.ai · zocks.io · finmate.ai · wealthbox.com · fathom.video · otter.ai
- **AI CRMs:** salesforce.com (Agentforce/FSC) · hubspot.com (Breeze) · attio.com (AI Attributes / Ask Attio) · learn.microsoft.com (Dynamics Copilot)
- **UK adviser AI:** advisoryai.com · aveni.ai (FinLLM) · saturnos.com · recordsure.com · intelliflo.com (IQ) · plannerpal.co.uk · multiply.ai
- **Emerging / planning:** Morgan Stanley AI Debrief · FP Alpha · Holistiplan · Conquest Planning (SAM) · Powder
- **Comparisons:** Kitces AI-notetaker research · XYPN "Battle of the Bots" · WealthTech Today 2026 buyer's guide
- **Regulatory:** FCA Consumer Duty / FG21-1 (vulnerability); Citywire on FCA annual-review consultation
