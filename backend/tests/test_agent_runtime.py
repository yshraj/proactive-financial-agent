"""Agent runtime: run/step persistence, the LangGraph graph, worker handler,
and the /api/agent endpoints (create + poll)."""
from __future__ import annotations

import json

import pytest

from tests.conftest import auth_headers_for, fake_gateway_result, make_org, seed_client


# ---------------------------------------------------------------------------
# Persistence (agent_runs service) — real Postgres + RLS
# ---------------------------------------------------------------------------


def test_run_and_step_lifecycle(clean_db, org_a):
    from app.services import agent_runs

    run = agent_runs.create(kind="copilot", input_payload={"query": "hi"}, ctx=org_a)
    assert run["status"] == agent_runs.PENDING
    assert run["input"] == {"query": "hi"}

    agent_runs.mark_running(run["id"], ctx=org_a)
    agent_runs.add_step(run["id"], seq=1, node="plan", label="Planning approach", ctx=org_a)
    agent_runs.finish_step(run["id"], seq=1, detail={"plan": []}, ctx=org_a)
    agent_runs.add_step(run["id"], seq=2, node="synthesize", label="Drafting answer", ctx=org_a)
    agent_runs.finish_step(run["id"], seq=2, ctx=org_a)
    agent_runs.finish(run["id"], output={"answer": "Done."}, ctx=org_a)

    loaded = agent_runs.get(run["id"], ctx=org_a)
    assert loaded["status"] == agent_runs.DONE
    assert loaded["output"]["answer"] == "Done."
    steps = agent_runs.get_steps(run["id"], ctx=org_a)
    assert [s["seq"] for s in steps] == [1, 2]
    assert steps[0]["detail"] == {"plan": []}
    assert all(s["status"] == "DONE" for s in steps)


def test_runs_are_org_isolated(clean_db, org_a, org_b):
    from app.services import agent_runs

    run = agent_runs.create(kind="copilot", input_payload={"query": "secret"}, ctx=org_a)
    assert agent_runs.get(run["id"], ctx=org_b) is None
    assert agent_runs.get_steps(run["id"], ctx=org_b) == []


def test_fail_records_public_error(clean_db, org_a):
    from app.services import agent_runs

    run = agent_runs.create(kind="copilot", input_payload={"query": "x"}, ctx=org_a)
    agent_runs.fail(run["id"], error="We couldn't generate AI results right now.", ctx=org_a)
    loaded = agent_runs.get(run["id"], ctx=org_a)
    assert loaded["status"] == agent_runs.ERROR
    assert "couldn't generate" in loaded["error"]


# ---------------------------------------------------------------------------
# Graph execution with a scripted LLM
# ---------------------------------------------------------------------------


def _script_llm(monkeypatch, responses: dict):
    """Patch the graph's complete_ex with per-purpose scripted results."""
    calls: list[dict] = []

    def fake(**kwargs):
        purpose = kwargs.get("purpose")
        calls.append(kwargs)
        handler = responses.get(purpose)
        if handler is None:
            raise AssertionError(f"Unexpected LLM purpose {purpose!r}")
        if callable(handler):
            return handler(kwargs)
        return handler

    monkeypatch.setattr("app.agents.graph.complete_ex", fake)
    return calls


def _mk_run(org, kind="copilot", query="Which reviews are overdue?", client_id=None):
    from app.services import agent_runs

    return agent_runs.create(
        kind=kind, input_payload={"query": query}, client_id=client_id, ctx=org
    )


def test_copilot_graph_happy_path(clean_db, org_a, monkeypatch):
    from app.agents.graph import run_agent
    from app.services import agent_runs

    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    _script_llm(monkeypatch, {
        "agent": fake_gateway_result(json.dumps({
            "tools": [{"name": "get_structured_context", "arguments": {}}],
            "reason": "Status question — structured records answer it",
        }), purpose="agent"),
        "chat": fake_gateway_result("Alan Partridge has no review on file.", purpose="chat"),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "grounded"}),
            purpose="reviewer",
        ),
    })

    run = _mk_run(org_a)
    output = run_agent(org_a, run)

    assert output["answer"] == "Alan Partridge has no review on file."
    assert output["review"]["verdict"] == "pass"
    steps = agent_runs.get_steps(run["id"], ctx=org_a)
    nodes = [s["node"] for s in steps]
    assert nodes == ["plan", "tool:get_structured_context", "synthesize", "review", "finalize"]
    assert all(s["status"] == "DONE" for s in steps)
    # The plan step records what the planner chose (audit/replay).
    assert steps[0]["detail"]["plan"][0]["name"] == "get_structured_context"


def test_review_failure_triggers_one_revision(clean_db, org_a, monkeypatch):
    from app.agents.graph import run_agent
    from app.services import agent_runs

    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    review_calls = {"n": 0}

    def reviewer(kwargs):
        review_calls["n"] += 1
        if review_calls["n"] == 1:
            return fake_gateway_result(json.dumps({
                "verdict": "fail",
                "issues": ["Invented a pension figure not present in context"],
                "notes": "ungrounded",
            }), purpose="reviewer")
        return fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "fixed"}), purpose="reviewer"
        )

    synth_calls = {"n": 0}

    def synth(kwargs):
        synth_calls["n"] += 1
        if synth_calls["n"] == 1:
            return fake_gateway_result("Alan has a £2m pension.", purpose="chat")
        return fake_gateway_result("Alan's pension value is not in your records.", purpose="chat")

    _script_llm(monkeypatch, {
        "agent": fake_gateway_result(json.dumps({
            "tools": [{"name": "get_structured_context", "arguments": {}}],
            "reason": "records",
        }), purpose="agent"),
        "chat": synth,
        "reviewer": reviewer,
    })

    run = _mk_run(org_a)
    output = run_agent(org_a, run)

    assert synth_calls["n"] == 2
    assert output["answer"] == "Alan's pension value is not in your records."
    assert output["review"]["verdict"] == "pass"
    nodes = [s["node"] for s in agent_runs.get_steps(run["id"], ctx=org_a)]
    assert nodes.count("synthesize") == 2
    assert nodes.count("review") == 2


def test_phantom_citation_fails_deterministically(clean_db, org_a, monkeypatch):
    """A draft citing [3] with no sources must fail review even if the LLM
    reviewer passes it — the deterministic check is not model-dependent."""
    from app.agents.graph import run_agent

    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    drafts = iter([
        "ISA allowance was discussed [3].",       # phantom citation
        "No document evidence found for this.",   # revision
    ])
    _script_llm(monkeypatch, {
        "agent": fake_gateway_result(json.dumps({
            "tools": [{"name": "get_structured_context", "arguments": {}}],
            "reason": "records",
        }), purpose="agent"),
        "chat": lambda kwargs: fake_gateway_result(next(drafts), purpose="chat"),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "looks fine"}),
            purpose="reviewer",
        ),
    })

    output = run_agent(org_a, _mk_run(org_a))
    assert output["answer"] == "No document evidence found for this."


def test_planner_failure_uses_default_plan(clean_db, org_a, monkeypatch):
    from app.agents.graph import run_agent
    from app.services.llm import AIUnavailableError

    seed_client(clean_db, org_a.org_id, "Alan Partridge")

    def planner(kwargs):
        raise AIUnavailableError("down")

    # Default copilot plan = structured context + document search; make the
    # search tool a no-op so the test doesn't need Qdrant.
    monkeypatch.setattr(
        "app.services.agent_tools.search_documents",
        lambda ctx, **kw: {"context": "", "sources": [], "summary": "0 excerpts"},
    )
    _script_llm(monkeypatch, {
        "agent": planner,
        "chat": fake_gateway_result("Answer from records.", purpose="chat"),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "ok"}), purpose="reviewer"
        ),
    })
    output = run_agent(org_a, _mk_run(org_a))
    assert output["answer"] == "Answer from records."
    assert output["plan_reason"].startswith("Default plan")


def test_reviewer_outage_is_skipped_not_fatal(clean_db, org_a, monkeypatch):
    from app.agents.graph import run_agent
    from app.services.llm import AIUnavailableError

    seed_client(clean_db, org_a.org_id, "Alan Partridge")

    def reviewer(kwargs):
        raise AIUnavailableError("down")

    _script_llm(monkeypatch, {
        "agent": fake_gateway_result(json.dumps({
            "tools": [{"name": "get_structured_context", "arguments": {}}],
            "reason": "records",
        }), purpose="agent"),
        "chat": fake_gateway_result("Grounded answer.", purpose="chat"),
        "reviewer": reviewer,
    })
    output = run_agent(org_a, _mk_run(org_a))
    assert output["answer"] == "Grounded answer."
    assert output["review"]["verdict"] == "skipped"


def test_brief_kind_uses_deterministic_plan_and_talking_points(clean_db, org_a, monkeypatch):
    from app.agents.graph import run_agent
    from app.services import agent_runs

    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")
    monkeypatch.setattr(
        "app.services.agent_tools.search_documents",
        lambda ctx, **kw: {"context": "", "sources": [], "summary": "0 excerpts"},
    )
    _script_llm(monkeypatch, {
        "brief": fake_gateway_result(
            "## Client snapshot\nAlan Partridge.\n---TALKING_POINTS---\nConfirm pension decision\nReview ISA usage",
            purpose="brief",
        ),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "ok"}), purpose="reviewer"
        ),
    })

    run = _mk_run(org_a, kind="brief", query="", client_id=client_id)
    output = run_agent(org_a, run)

    assert output["answer"].startswith("## Client snapshot")
    assert output["talking_points"] == ["Confirm pension decision", "Review ISA usage"]
    nodes = [s["node"] for s in agent_runs.get_steps(run["id"], ctx=org_a)]
    # Deterministic brief plan: records + scores + documents (no LLM planner).
    assert "tool:get_structured_context" in nodes
    assert "tool:get_client_scores" in nodes
    assert "tool:search_documents" in nodes


# ---------------------------------------------------------------------------
# API + worker end-to-end (background drain runs after the response)
# ---------------------------------------------------------------------------


def _script_api_llm(monkeypatch):
    return _script_llm(monkeypatch, {
        "agent": fake_gateway_result(json.dumps({
            "tools": [{"name": "get_structured_context", "arguments": {}}],
            "reason": "records",
        }), purpose="agent"),
        "chat": fake_gateway_result("Run answer.", purpose="chat"),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "ok"}), purpose="reviewer"
        ),
    })


def test_agent_run_end_to_end_via_api(api_client, clean_db, org_a, monkeypatch):
    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    _script_api_llm(monkeypatch)
    headers = {**auth_headers_for(org_a), "X-Idempotency-Key": "agent-run-1"}

    created = api_client.post(
        "/api/agent/runs", headers=headers, json={"kind": "copilot", "query": "What's overdue?"}
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["run_id"]
    conversation_id = created.json()["conversation_id"]
    assert conversation_id

    polled = api_client.get(f"/api/agent/runs/{run_id}", headers=auth_headers_for(org_a))
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "DONE", body
    assert body["output"]["answer"] == "Run answer."
    assert [s["node"] for s in body["steps"]] == [
        "plan", "tool:get_structured_context", "synthesize", "review", "finalize",
    ]

    # One credit committed for the copilot run.
    summary = api_client.get("/api/credits", headers=auth_headers_for(org_a)).json()
    assert summary["used"] == 1

    # The exchange landed in the conversation thread.
    messages = api_client.get(
        f"/api/chat/conversations/{conversation_id}/messages", headers=auth_headers_for(org_a)
    ).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Run answer."


def test_agent_run_validation_errors(api_client, clean_db, org_a):
    headers = auth_headers_for(org_a)
    no_query = api_client.post("/api/agent/runs", headers=headers, json={"kind": "copilot"})
    assert no_query.status_code == 400
    no_client = api_client.post("/api/agent/runs", headers=headers, json={"kind": "brief"})
    assert no_client.status_code == 400
    bad_kind = api_client.post(
        "/api/agent/runs", headers=headers, json={"kind": "world-domination", "query": "x"}
    )
    assert bad_kind.status_code == 422


def test_agent_run_poll_is_org_scoped(api_client, clean_db, org_a, monkeypatch):
    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    _script_api_llm(monkeypatch)
    headers = {**auth_headers_for(org_a), "X-Idempotency-Key": "agent-run-iso"}
    created = api_client.post(
        "/api/agent/runs", headers=headers, json={"kind": "copilot", "query": "What's due?"}
    )
    run_id = created.json()["run_id"]

    org_b = make_org(clean_db, "Org B Intruder")
    foreign = api_client.get(f"/api/agent/runs/{run_id}", headers=auth_headers_for(org_b))
    assert foreign.status_code == 404


def test_failed_run_releases_credits_and_reports_cleanly(
    api_client, clean_db, org_a, monkeypatch
):
    from app.services.llm import AIUnavailableError

    seed_client(clean_db, org_a.org_id, "Alan Partridge")

    def always_down(**kwargs):
        raise AIUnavailableError(
            "We couldn't generate AI results right now. Please try again in a few minutes."
        )

    monkeypatch.setattr("app.agents.graph.complete_ex", always_down)
    # Make retries immediate-fail (attempts start at 1 per claim); force one
    # attempt so the drain doesn't loop three times in-process.
    monkeypatch.setattr("app.services.agent_tools.search_documents",
                        lambda ctx, **kw: {"context": "", "sources": [], "summary": "0"})

    headers = {**auth_headers_for(org_a), "X-Idempotency-Key": "agent-run-fail"}
    created = api_client.post(
        "/api/agent/runs", headers=headers, json={"kind": "copilot", "query": "boom"}
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]

    # Drain to exhaustion: the in-process background task retried once; run the
    # worker drain until the job is terminal.
    from app.context import set_current_tenant
    from app.worker import drain_queue

    set_current_tenant(None)
    for _ in range(4):
        drain_queue(lambda: 10_000_000)

    polled = api_client.get(f"/api/agent/runs/{run_id}", headers=auth_headers_for(org_a))
    body = polled.json()
    assert body["status"] == "ERROR"
    assert "couldn't generate AI results" in body["error"]
    assert "AIUnavailableError" not in (body["error"] or "")

    # Reservation released: nothing consumed.
    summary = api_client.get("/api/credits", headers=auth_headers_for(org_a)).json()
    assert summary["used"] == 0


@pytest.mark.parametrize("kind,feature_used", [("brief", 5)])
def test_brief_run_costs_report_credits(api_client, clean_db, org_a, monkeypatch, kind, feature_used):
    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")
    monkeypatch.setattr(
        "app.services.agent_tools.search_documents",
        lambda ctx, **kw: {"context": "", "sources": [], "summary": "0 excerpts"},
    )
    _script_llm(monkeypatch, {
        "brief": fake_gateway_result("## Client snapshot\nX.", purpose="brief"),
        "reviewer": fake_gateway_result(
            json.dumps({"verdict": "pass", "issues": [], "notes": "ok"}), purpose="reviewer"
        ),
    })
    headers = {**auth_headers_for(org_a), "X-Idempotency-Key": "agent-brief-1"}
    created = api_client.post(
        "/api/agent/runs", headers=headers, json={"kind": kind, "client_id": client_id}
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    polled = api_client.get(f"/api/agent/runs/{run_id}", headers=auth_headers_for(org_a))
    assert polled.json()["status"] == "DONE"
    summary = api_client.get("/api/credits", headers=auth_headers_for(org_a)).json()
    assert summary["used"] == feature_used
