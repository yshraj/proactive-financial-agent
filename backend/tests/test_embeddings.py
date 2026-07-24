"""Embedding provider abstraction (services/embeddings.py) + collection wiring."""
from __future__ import annotations

import importlib

import pytest

from app.services import embeddings


@pytest.fixture(autouse=True)
def _clean():
    embeddings.reset_for_tests()
    yield
    embeddings.reset_for_tests()


def test_fastembed_is_the_default_provider(monkeypatch):
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    assert embeddings.provider() == "fastembed"
    assert embeddings.model_name() == "BAAI/bge-small-en-v1.5"
    assert embeddings.vector_size() == 384


def test_openai_provider_is_opt_in(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
    assert embeddings.provider() == "openai"
    assert embeddings.model_name() == "text-embedding-3-small"
    assert embeddings.vector_size() == 1536


def test_unknown_provider_falls_back_to_fastembed(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "quantum-vibes")
    assert embeddings.provider() == "fastembed"


def test_collection_name_follows_provider(monkeypatch):
    from app.services import config

    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    importlib.reload(config)
    assert config.QDRANT_COLLECTION == "client_memory_bge384"

    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
    importlib.reload(config)
    assert config.QDRANT_COLLECTION == "client_memory"

    monkeypatch.setenv("QDRANT_COLLECTION", "my_explicit_name")
    importlib.reload(config)
    assert config.QDRANT_COLLECTION == "my_explicit_name"

    # Restore module state for the rest of the suite.
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    importlib.reload(config)


def test_embed_texts_uses_local_model(monkeypatch):
    class FakeModel:
        def embed(self, texts):
            import numpy as np

            for _ in texts:
                yield np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(embeddings, "_get_fastembed", lambda: FakeModel())
    vectors = embeddings.embed_texts(["hello", "world"])
    assert len(vectors) == 2
    assert vectors[0] == pytest.approx([0.1, 0.2, 0.3])
    # Plain lists (JSON/Qdrant friendly), not numpy arrays.
    assert isinstance(vectors[0], list)


def test_embed_texts_empty_is_noop():
    assert embeddings.embed_texts([]) == []


def test_openai_branch_calls_legacy_client(monkeypatch):
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")

    class FakeData:
        def __init__(self, vec):
            self.embedding = vec

    class FakeResponse:
        data = [FakeData([0.5] * 3)]
        usage = None

    class FakeClient:
        class embeddings:  # noqa: N801 - mimic openai client shape
            @staticmethod
            def create(input, model):
                assert model == "text-embedding-3-small"
                return FakeResponse()

    monkeypatch.setattr("app.services.clients.get_openai_client", lambda: FakeClient())
    vectors = embeddings.embed_texts(["hi"])
    assert vectors == [[0.5, 0.5, 0.5]]


def test_query_embedding_goes_through_abstraction(monkeypatch):
    calls = []

    def fake_embed(texts):
        calls.append(texts)
        return [[0.9, 0.8]]

    monkeypatch.setattr("app.services.rag_context.embed_texts", fake_embed)
    from app.services.rag_context import embed_query

    assert embed_query("which reviews are overdue?") == [0.9, 0.8]
    assert calls == [["which reviews are overdue?"]]
