"""
Access-log level policy (app.main._is_low_value_access_log / RequestContextMiddleware):

High-frequency, low-diagnostic-value GET polling endpoints (dashboard pulse,
credit-balance checks, agent-run / upload-job status polls) are demoted to
DEBUG on success so CloudWatch log ingestion doesn't scale linearly with
polling traffic. Every error and every mutation (non-GET) must still log at
INFO regardless of path — that invariant is what these tests protect.
"""
from __future__ import annotations

import logging

from app.main import _is_low_value_access_log
from tests.conftest import auth_headers_for


def test_low_value_get_paths_are_demoted():
    assert _is_low_value_access_log("GET", "/api/monitor/pulse", 200) is True
    assert _is_low_value_access_log("GET", "/api/credits", 200) is True
    assert _is_low_value_access_log("GET", "/api/credits/history", 200) is True
    assert _is_low_value_access_log("GET", "/api/agent/runs/abc-123", 200) is True
    assert _is_low_value_access_log("GET", "/api/ingest/jobs/job-1", 200) is True


def test_errors_on_low_value_paths_are_never_demoted():
    """A polling endpoint that fails is exactly the case worth keeping at INFO."""
    assert _is_low_value_access_log("GET", "/api/monitor/pulse", 500) is False
    assert _is_low_value_access_log("GET", "/api/credits", 429) is False
    assert _is_low_value_access_log("GET", "/api/agent/runs/abc-123", 404) is False


def test_mutations_are_never_demoted_even_on_a_low_value_prefix():
    assert _is_low_value_access_log("POST", "/api/agent/runs/abc-123", 200) is False
    assert _is_low_value_access_log("PATCH", "/api/credits", 200) is False


def test_unrelated_paths_are_not_demoted():
    assert _is_low_value_access_log("GET", "/api/monitor/clients", 200) is False
    assert _is_low_value_access_log("GET", "/api/chat", 200) is False
    assert _is_low_value_access_log("POST", "/api/ingest/upload-async", 202) is False


def test_credits_endpoint_logs_at_debug_not_info(api_client, clean_db, org_a, caplog):
    """End-to-end: a real request through the middleware lands at DEBUG."""
    with caplog.at_level(logging.DEBUG, logger="jarvis.access"):
        resp = api_client.get("/api/credits", headers=auth_headers_for(org_a))
    assert resp.status_code == 200
    records = [r for r in caplog.records if r.name == "jarvis.access"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG


def test_clients_endpoint_still_logs_at_info(api_client, clean_db, org_a, caplog):
    """A non-polling endpoint is unaffected by the demotion list."""
    with caplog.at_level(logging.DEBUG, logger="jarvis.access"):
        resp = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_a))
    assert resp.status_code == 200
    records = [r for r in caplog.records if r.name == "jarvis.access"]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
