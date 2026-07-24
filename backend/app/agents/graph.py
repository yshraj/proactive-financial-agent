"""
The agent graph: plan → gather → synthesize → review → finalize.

One LangGraph ``StateGraph`` powers both run kinds:

- ``copilot`` — an LLM planner picks 1-3 read-only tools, the gathered
  context is synthesized into a cited answer, and a *different model family*
  reviews it for grounding/citation/advice-boundary violations, with one
  revision loop on failure.
- ``brief`` — the same graph with a deterministic plan (structured records +
  client scores + document search) and the brief prompt/talking-points
  output shape.

Design constraints (enforced in the runtime, not the prompt):
- hard budgets: ≤3 tools per plan, ≤1 revision, bounded max_tokens per node;
- every node and every tool call is recorded as an ``agent_steps`` row —
  the real timeline the frontend polls, and the audit/replay record;
- the graph state is JSON-serializable and checkpointed to
  ``agent_runs.state`` after every node (best-effort) for replay/debugging;
- the TenantContext travels by closure, never through model-visible state:
  tools are RLS-scoped and the planner cannot widen the run's client scope;
- LLM failures degrade by node: planner → deterministic default plan,
  reviewer → recorded as skipped; only synthesis failure fails the run
  (with fixed public copy).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

try:  # Python 3.9: TypedDict from typing_extensions for total=False support
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

from app.context import TenantContext
from app.services import agent_runs, agent_tools, tracing
from app.services.llm import AIUnavailableError, complete_ex
from app.services.model_gateway import family_of
from app.services.prompts import (
    AGENT_PLANNER_SYSTEM,
    AGENT_REVIEWER_SYSTEM,
    BRIEF_SYSTEM,
    CHAT_SYSTEM,
    brief_user_message,
    chat_user_message,
)
from app.services.rag_context import brief_retrieval_query
from app.services.safety import contains_prompt_echo, sanitize_user_query

logger = logging.getLogger("jarvis.agents")

MAX_PLAN_TOOLS = 3
MAX_REVISIONS = 1

_FRIENDLY_TOOL_LABELS = {
    "search_documents": "Searching documents",
    "get_structured_context": "Loading structured records",
    "get_book_analytics": "Computing book analytics",
    "get_client_scores": "Scoring client engagement",
    "list_upcoming_alerts": "Checking upcoming alerts",
}


class AgentState(TypedDict, total=False):
    kind: str
    query: str
    client_id: Optional[str]
    client_name: str
    history: str
    plan: list
    plan_reason: str
    structured_context: str
    rag_context: str
    sources: list
    analysis: list
    draft: str
    generator_label: str
    generator_family: str
    review_verdict: str
    review_issues: list
    review_notes: str
    revisions: int
    answer: str
    talking_points: list
    model_labels: dict


def _parse_json_block(raw: str) -> Optional[dict]:
    """Extract the first JSON object from model output (fence-tolerant)."""
    if not raw:
        return None
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class _Recorder:
    """Sequenced step recording for one run (steps are the visible timeline)."""

    def __init__(self, ctx: TenantContext, run_id: str):
        self._ctx = ctx
        self._run_id = run_id
        self._seq = 0
        self._names: dict = {}  # seq -> (node, label)

    def start(self, node: str, label: str, detail: Optional[dict] = None) -> int:
        self._seq += 1
        seq = self._seq
        self._names[seq] = (node, label)
        try:
            agent_runs.add_step(
                self._run_id, seq=seq, node=node, label=label, detail=detail, ctx=self._ctx
            )
        except Exception:  # noqa: BLE001 - timeline is best-effort, never fatal
            logger.exception("Failed to record step start")
        return seq

    def finish(self, seq: int, *, status: str = "DONE", detail: Optional[dict] = None) -> None:
        try:
            agent_runs.finish_step(
                self._run_id, seq=seq, status=status, detail=detail, ctx=self._ctx
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record step finish")
        node, label = self._names.get(seq, (f"step-{seq}", f"seq {seq}"))
        tracing.record_step(node=node, label=label, status=status, detail=detail)

    def checkpoint(self, state: dict) -> None:
        try:
            snapshot = {k: v for k, v in state.items() if k != "history"}
            agent_runs.save_state(self._run_id, state=snapshot, ctx=self._ctx)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to checkpoint state")


def _default_plan(state: AgentState) -> list:
    """Deterministic plan used for briefs and as the planner fallback."""
    if state.get("kind") == "brief":
        plan: list = [
            {"name": "get_structured_context", "arguments": {}},
            {"name": "get_client_scores", "arguments": {}},
            {
                "name": "search_documents",
                "arguments": {
                    "query": brief_retrieval_query(state.get("client_name") or "client", [])
                },
            },
        ]
        return plan
    plan = [{"name": "get_structured_context", "arguments": {}}]
    if (state.get("query") or "").strip():
        plan.append({"name": "search_documents", "arguments": {"query": state["query"]}})
    return plan


def build_graph(ctx: TenantContext, run_id: str, recorder: Optional[_Recorder] = None):
    """Compile the agent graph with ctx/run bound by closure (never in state)."""
    rec = recorder or _Recorder(ctx, run_id)

    # -- plan ---------------------------------------------------------------
    def plan_node(state: AgentState) -> dict:
        seq = rec.start("plan", "Planning approach")
        labels = dict(state.get("model_labels") or {})
        if state.get("kind") == "brief":
            plan = _default_plan(state)
            rec.finish(seq, detail={"plan": plan, "reason": "Standard pre-meeting brief workflow"})
            update = {"plan": plan, "plan_reason": "Standard pre-meeting brief workflow"}
            rec.checkpoint({**state, **update})
            return update
        plan: list = []
        reason = ""
        try:
            result = complete_ex(
                messages=[
                    {"role": "system", "content": AGENT_PLANNER_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Scope: {'one client' if state.get('client_id') else 'whole book'}\n"
                            f"<user_query>\n{sanitize_user_query(state.get('query') or '')}\n"
                            "</user_query>"
                        ),
                    },
                ],
                max_tokens=300,
                purpose="agent",
                temperature=0,
                response_format={"type": "json_object"},
            )
            labels["plan"] = result.label
            data = _parse_json_block(result.content) or {}
            reason = str(data.get("reason") or "")[:200]
            for item in data.get("tools") or []:
                name = (item or {}).get("name")
                if name in agent_tools.TOOL_NAMES and len(plan) < MAX_PLAN_TOOLS:
                    args = item.get("arguments")
                    plan.append({"name": name, "arguments": args if isinstance(args, dict) else {}})
        except AIUnavailableError:
            logger.warning("Planner unavailable; using deterministic default plan")
        except Exception:  # noqa: BLE001 - any planner weirdness → default plan
            logger.exception("Planner failed; using deterministic default plan")
        if not plan:
            plan = _default_plan(state)
            reason = reason or "Default plan (planner unavailable)"
        rec.finish(seq, detail={"plan": plan, "reason": reason, "model": labels.get("plan")})
        update = {"plan": plan, "plan_reason": reason, "model_labels": labels}
        rec.checkpoint({**state, **update})
        return update

    # -- gather (tool execution) ---------------------------------------------
    def gather_node(state: AgentState) -> dict:
        structured = state.get("structured_context") or ""
        rag = state.get("rag_context") or ""
        sources = list(state.get("sources") or [])
        analysis = list(state.get("analysis") or [])
        for item in (state.get("plan") or [])[:MAX_PLAN_TOOLS]:
            name = item.get("name")
            args = item.get("arguments") or {}
            label = _FRIENDLY_TOOL_LABELS.get(name, name or "Tool")
            seq = rec.start(f"tool:{name}", label, detail={"arguments": args})
            try:
                outcome = agent_tools.execute_tool(
                    ctx, name, args, client_id=state.get("client_id")
                )
            except Exception:  # noqa: BLE001 - one broken tool must not kill the run
                logger.exception("Tool %s failed", name)
                rec.finish(seq, status="ERROR", detail={"error": "Tool failed"})
                continue
            if name == "search_documents":
                rag = outcome.get("context") or ""
                sources = outcome.get("sources") or []
            elif name == "get_structured_context":
                structured = outcome.get("context") or ""
            else:
                analysis.append({"tool": name, "result": {
                    k: v for k, v in outcome.items() if k != "summary"
                }})
            rec.finish(seq, detail={"summary": outcome.get("summary", "done")})
        update = {
            "structured_context": structured,
            "rag_context": rag,
            "sources": sources,
            "analysis": analysis,
        }
        rec.checkpoint({**state, **update})
        return update

    # -- synthesize -----------------------------------------------------------
    def synthesize_node(state: AgentState) -> dict:
        revising = bool(state.get("review_verdict") == "fail")
        seq = rec.start(
            "synthesize",
            "Revising after review" if revising else (
                "Drafting brief" if state.get("kind") == "brief" else "Drafting answer"
            ),
        )
        structured = state.get("structured_context") or ""
        if state.get("analysis"):
            analysis_text = "\n".join(
                f"- {a['tool']}: {json.dumps(a['result'], default=str)[:800]}"
                for a in state["analysis"]
            )
            structured = f"{structured}\n\nDeterministic analysis (trusted):\n{analysis_text}"
        if revising:
            issues = "; ".join(state.get("review_issues") or []) or "unspecified issues"
            structured += (
                "\n\nIMPORTANT — a compliance reviewer rejected the previous draft for: "
                f"{issues}. Rewrite it fixing these problems. Use only facts from the context."
            )

        if state.get("kind") == "brief":
            user = brief_user_message(
                client_name=state.get("client_name") or "Client",
                structured=structured or "No structured data on file.",
                documents=state.get("rag_context") or "",
            )
            system, purpose, max_tokens = BRIEF_SYSTEM, "brief", 1400
        else:
            user = chat_user_message(
                structured=structured,
                documents=state.get("rag_context") or "",
                query=state.get("query") or "",
                history=state.get("history") or "",
            )
            system, purpose, max_tokens = CHAT_SYSTEM, "chat", 900

        try:
            result = complete_ex(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                purpose=purpose,  # type: ignore[arg-type]
            )
        except AIUnavailableError:
            rec.finish(seq, status="ERROR", detail={"error": "AI providers unavailable"})
            raise
        labels = dict(state.get("model_labels") or {})
        labels["synthesize"] = result.label
        rec.finish(seq, detail={"model": result.label, "chars": len(result.content)})
        update = {
            "draft": result.content,
            "generator_label": result.label,
            "generator_family": family_of(result.provider, result.model),
            "model_labels": labels,
            "revisions": int(state.get("revisions") or 0) + (1 if revising else 0),
            # Reset the verdict so the review node re-evaluates the new draft.
            "review_verdict": "",
            "review_issues": [],
        }
        rec.checkpoint({**state, **update})
        return update

    # -- review (cross-model critique + deterministic citation check) ---------
    def review_node(state: AgentState) -> dict:
        seq = rec.start("review", "Compliance review")
        draft = state.get("draft") or ""
        sources = state.get("sources") or []
        issues: list = []

        # Deterministic: every [n] citation must reference a real source.
        cited = {int(m) for m in re.findall(r"\[(\d{1,2})\]", draft)}
        valid = {int(s.get("ref") or 0) for s in sources}
        phantom = sorted(c for c in cited if c not in valid)
        if phantom:
            issues.append(f"Draft cites non-existent source(s): {phantom}")

        # Deterministic: a draft must never echo the system persona verbatim —
        # that is a prompt-leak (see safety.contains_prompt_echo). Force a revision.
        leaked = contains_prompt_echo(draft)
        if leaked:
            issues.append("Draft discloses the system prompt/persona.")

        verdict = "pass"
        notes = ""
        labels = dict(state.get("model_labels") or {})
        try:
            result = complete_ex(
                messages=[
                    {"role": "system", "content": AGENT_REVIEWER_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            "=== CONTEXT the drafting model saw ===\n"
                            f"{(state.get('structured_context') or '')[:3000]}\n\n"
                            f"{(state.get('rag_context') or '')[:3000]}\n\n"
                            f"=== DRAFT ===\n{draft[:4000]}"
                        ),
                    },
                ],
                max_tokens=300,
                purpose="reviewer",
                temperature=0,
                response_format={"type": "json_object"},
            )
            labels["review"] = result.label
            data = _parse_json_block(result.content) or {}
            if str(data.get("verdict") or "").lower() == "fail":
                verdict = "fail"
                issues.extend(str(i)[:200] for i in (data.get("issues") or [])[:5])
            notes = str(data.get("notes") or "")[:300]
        except AIUnavailableError:
            verdict = "skipped"
            notes = "Reviewer unavailable — deterministic checks only."
        except Exception:  # noqa: BLE001
            logger.exception("Reviewer failed; falling back to deterministic checks")
            verdict = "skipped"
            notes = "Reviewer unavailable — deterministic checks only."

        if phantom or leaked:
            verdict = "fail"
        rec.finish(
            seq,
            status="DONE",
            detail={
                "verdict": verdict,
                "issues": issues,
                "notes": notes,
                "model": labels.get("review"),
            },
        )
        update = {
            "review_verdict": verdict,
            "review_issues": issues,
            "review_notes": notes,
            "model_labels": labels,
        }
        rec.checkpoint({**state, **update})
        return update

    def after_review(state: AgentState) -> str:
        if state.get("review_verdict") == "fail" and int(state.get("revisions") or 0) < MAX_REVISIONS:
            return "revise"
        return "done"

    # -- finalize --------------------------------------------------------------
    def finalize_node(state: AgentState) -> dict:
        seq = rec.start("finalize", "Finalising")
        draft = (state.get("draft") or "").strip()
        talking_points: list = []
        if state.get("kind") == "brief" and "---TALKING_POINTS---" in draft:
            brief_part, points_part = draft.split("---TALKING_POINTS---", 1)
            draft = brief_part.strip()
            for line in points_part.strip().splitlines():
                line = line.strip().lstrip("-•* ").strip()
                if line:
                    talking_points.append(line)
            talking_points = talking_points[:5]
        if not draft:
            draft = "I couldn't find a clear answer from the available context."
        rec.finish(seq)
        update = {"answer": draft, "talking_points": talking_points}
        rec.checkpoint({**state, **update})
        return update

    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("gather", gather_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("review", review_node)
    graph.add_node("finalize", finalize_node)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "gather")
    graph.add_edge("gather", "synthesize")
    graph.add_edge("synthesize", "review")
    graph.add_conditional_edges("review", after_review, {"revise": "synthesize", "done": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


def run_agent(ctx: TenantContext, run: dict[str, Any]) -> dict[str, Any]:
    """Execute one persisted agent run and return its output payload.

    The caller (worker handler) owns run/job status transitions and credits;
    this function owns the graph execution and the step timeline.
    """
    from app.services import conversations

    run_id = run["id"]
    payload = run.get("input") or {}
    kind = run.get("kind") or "copilot"
    client_id = run.get("client_id")

    client_name = ""
    if client_id:
        from app.db import get_cursor

        with get_cursor(ctx=ctx) as cur:
            cur.execute(
                "SELECT full_name FROM clients WHERE id = %s AND org_id = %s",
                (client_id, ctx.org_id),
            )
            row = cur.fetchone()
        client_name = ((row or {}).get("full_name") or "").strip()

    history = ""
    conversation_id = run.get("conversation_id")
    if kind == "copilot" and conversation_id:
        owner_ctx = TenantContext(
            org_id=ctx.org_id, user_id=run.get("user_id"), role="system"
        )
        history = conversations.format_history(
            conversations.get_messages(conversation_id, ctx=owner_ctx)
        )

    initial: AgentState = {
        "kind": kind,
        "query": sanitize_user_query(str(payload.get("query") or "")),
        "client_id": client_id,
        "client_name": client_name,
        "history": history,
        "revisions": 0,
        "model_labels": {},
    }
    tracing.install()
    tracing.start_run_trace(
        run_id=run_id, kind=kind, org_id=ctx.org_id, query=initial.get("query") or ""
    )
    try:
        app = build_graph(ctx, run_id)
        final_state = app.invoke(initial, config={"recursion_limit": 16})
    except Exception as exc:
        tracing.end_run_trace(error=str(exc)[:300])
        raise

    output = {
        "answer": final_state.get("answer") or "",
        "talking_points": final_state.get("talking_points") or [],
        "sources": final_state.get("sources") or [],
        "review": {
            "verdict": final_state.get("review_verdict") or "skipped",
            "issues": final_state.get("review_issues") or [],
            "notes": final_state.get("review_notes") or "",
        },
        "model_labels": final_state.get("model_labels") or {},
        "plan_reason": final_state.get("plan_reason") or "",
    }
    tracing.end_run_trace(output={"answer_chars": len(output["answer"]),
                                  "review": output["review"]["verdict"]})
    return output
