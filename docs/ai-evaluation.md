# AI evaluation framework

How we measure and defend the quality of KritiFin's AI outputs. The goal is a
cheap, deterministic offline gate in CI plus a periodic online gate against a
live model, so prompt/RAG changes cannot silently regress grounding, citations,
or the injection posture.

## What we measure

| Metric | Definition | Where measured | Target |
|--------|-----------|----------------|--------|
| Grounding / faithfulness | % of answer claims supported by the provided context | offline (LLM-judge) + spot online | ≥ 0.95 |
| Citation accuracy | Cited `[n]` maps to a real retrieved source that supports the claim | offline structural + online judge | ≥ 0.95 |
| Hallucination rate | % answers asserting facts (clients, £ amounts, dates) absent from context | online judge | ≤ 2% |
| Retrieval relevance | Retrieved chunk belongs to the queried org/client and topic | offline (fixtures) | 100% tenant, ≥ 0.8 topical |
| Injection resistance | Adversarial document/query does not change behaviour | offline (this suite) + online | 100% |
| Refusal correctness | "Not in your records" when context is empty; no regulated advice | offline prompt contract + online | ≥ 0.98 |
| Latency | p50/p95 end-to-end and first-token (once streaming lands) | online (telemetry) | p95 < 6s; first-token < 2s |
| Token cost | Tokens per request by purpose, cost per active adviser | online (usage counters) | tracked; budget-alarmed |

## Offline evaluation (in CI, no model calls)

`backend/tests/test_ai_quality.py` locks the deterministic guardrails:

- prompt-injection sanitisation over an adversarial corpus (`INJECTION_CORPUS`),
  which is the seed injection eval set;
- the prompt trust contract (untrusted-document framing, mandatory citations,
  no-invention, no-regulated-advice, human-review sign-off, JSON-only
  extraction);
- context-assembly delimiting and query wrapping;
- `PROMPT_VERSION` cache-busting on any template edit.

These run on every PR and are effectively free. Any prompt change that weakens
a guardrail fails the build (as the "disregard the above" gap did when this
suite was introduced — the filter was tightened in the same change).

## Prompt regression tests

Because prompts are centralised in `services/prompts.py` and hashed into
`PROMPT_VERSION`, a template edit is visible in the diff and flips the version.
The contract tests above are the regression harness: extend them whenever a new
rule is added to a prompt (e.g. a new citation format), so the rule is pinned.

## Golden dataset (offline, model-optional)

Store curated `(context, query, expected_properties)` cases under
`backend/tests/fixtures/ai_golden/` (JSONL). Properties are assertions, not
exact strings (LLM output is non-deterministic):

```json
{"id": "isa-booklevel", "scope": "all",
 "context_fixture": "book_two_clients",
 "query": "Who has ISA allowance left this tax year?",
 "must_mention": ["Alan"], "must_not_mention": ["Sarah"],
 "must_cite": true, "must_refuse": false}
```

A `RUN_AI_EVAL=1` marker (skipped by default in CI) runs these against the
configured model and scores with a rubric-based LLM judge. Gate the nightly
job, not PRs, to control cost and flakiness.

## Online evaluation

- **Telemetry** (already wired): per-request model, token counts, latency, and
  org are logged; a usage-counter table aggregates cost per org/day. Add
  grounding/citation sampling by logging (with PII scrubbed) a hash of the
  retrieved source ids alongside each answer for later judged sampling.
- **Sampled judging**: nightly, sample N production chat/brief answers
  (redacted) and run the faithfulness + citation rubric; alert if grounding
  drops below target.
- **Canary prompts**: a fixed set of book-level questions run against staging
  after each deploy; compare answers' structural properties (cites present,
  refusal on empty context) to catch prompt/retrieval regressions pre-promote.

## Benchmark suite (performance)

`load/k6-baseline.js` covers latency/error-rate under load. Extend with a chat
scenario that records first-token time once SSE streaming lands (Phase 2).

## Ownership

The offline suite is owned by whoever edits prompts/RAG — it must stay green.
The online judge + canaries are an ops responsibility reviewed in the weekly
ops review alongside error budget and LLM spend.
