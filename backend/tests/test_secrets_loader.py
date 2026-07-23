"""Cold-start SSM secrets loading (app/secrets_loader.py). Unit tests: boto3
is faked — no AWS calls."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app import secrets_loader


@pytest.fixture(autouse=True)
def _reset_loader(monkeypatch):
    """Each test starts unloaded and with no prefix configured."""
    monkeypatch.setattr(secrets_loader, "_loaded", False)
    monkeypatch.delenv("SECRETS_SSM_PREFIX", raising=False)


def _page(params: dict[str, str], next_token: str | None = None) -> dict:
    page = {
        "Parameters": [
            {"Name": f"/kritifin/test/{name}", "Value": value}
            for name, value in params.items()
        ]
    }
    if next_token:
        page["NextToken"] = next_token
    return page


def _client_returning(*pages: dict) -> MagicMock:
    client = MagicMock()
    client.get_parameters_by_path.side_effect = list(pages)
    return client


def test_noop_without_prefix():
    with patch("boto3.client") as boto:
        assert secrets_loader.load_secrets() == 0
    boto.assert_not_called()


def test_loads_parameters_into_env(monkeypatch):
    monkeypatch.setenv("SECRETS_SSM_PREFIX", "/kritifin/test")
    monkeypatch.delenv("FAKE_SECRET_A", raising=False)
    client = _client_returning(_page({"FAKE_SECRET_A": "s3cret"}))
    with patch("boto3.client", return_value=client):
        assert secrets_loader.load_secrets() == 1
    assert os.environ.pop("FAKE_SECRET_A") == "s3cret"
    # Decryption must be requested: values are SecureStrings.
    kwargs = client.get_parameters_by_path.call_args.kwargs
    assert kwargs["WithDecryption"] is True
    assert kwargs["Path"] == "/kritifin/test"


def test_existing_env_var_wins(monkeypatch):
    monkeypatch.setenv("SECRETS_SSM_PREFIX", "/kritifin/test")
    monkeypatch.setenv("FAKE_SECRET_B", "local-override")
    client = _client_returning(_page({"FAKE_SECRET_B": "from-ssm"}))
    with patch("boto3.client", return_value=client):
        assert secrets_loader.load_secrets() == 0
    assert os.environ["FAKE_SECRET_B"] == "local-override"


def test_follows_pagination(monkeypatch):
    monkeypatch.setenv("SECRETS_SSM_PREFIX", "/kritifin/test")
    for name in ("FAKE_PAGE_1", "FAKE_PAGE_2"):
        monkeypatch.delenv(name, raising=False)
    client = _client_returning(
        _page({"FAKE_PAGE_1": "one"}, next_token="t"),
        _page({"FAKE_PAGE_2": "two"}),
    )
    with patch("boto3.client", return_value=client):
        assert secrets_loader.load_secrets() == 2
    assert os.environ.pop("FAKE_PAGE_1") == "one"
    assert os.environ.pop("FAKE_PAGE_2") == "two"
    assert client.get_parameters_by_path.call_count == 2


def test_fetch_failure_is_fatal(monkeypatch):
    monkeypatch.setenv("SECRETS_SSM_PREFIX", "/kritifin/test")
    client = MagicMock()
    client.get_parameters_by_path.side_effect = ConnectionError("ssm down")
    with patch("boto3.client", return_value=client):
        with pytest.raises(RuntimeError, match="Failed to load secrets"):
            secrets_loader.load_secrets()


def test_second_call_is_noop(monkeypatch):
    monkeypatch.setenv("SECRETS_SSM_PREFIX", "/kritifin/test")
    monkeypatch.delenv("FAKE_SECRET_C", raising=False)
    client = _client_returning(_page({"FAKE_SECRET_C": "v"}), _page({}))
    with patch("boto3.client", return_value=client):
        secrets_loader.load_secrets()
        assert secrets_loader.load_secrets() == 0
    os.environ.pop("FAKE_SECRET_C", None)
    assert client.get_parameters_by_path.call_count == 1
