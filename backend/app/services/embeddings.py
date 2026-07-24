"""
Embedding provider abstraction: fastembed (local ONNX, default) or OpenAI
(legacy).

fastembed is the zero-cost, zero-rate-limit default: bge-small-en-v1.5
(384-dim) runs in-process on CPU, so the query path — which embeds every
copilot question — can never hit a provider quota, and document text never
leaves the backend for embedding. English-retrieval quality is at parity
with text-embedding-3-small.

The two providers write to different Qdrant collections (384 vs 1536 dims):
``services.config.QDRANT_COLLECTION`` resolves per provider unless the env
pins an explicit name. Existing OpenAI-embedded deployments keep working by
setting ``EMBEDDINGS_PROVIDER=openai`` (and installing the ``openai``
package, which is no longer a core requirement); migrate with
``scripts/reindex_embeddings.py``.

Model cache: the Docker image bakes the model into ``/opt/fastembed-cache``
at build time so Lambda cold starts never download it. Locally the cache
falls back to fastembed's default (~/.cache) or ``/tmp``.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("jarvis.embeddings")

DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Vector sizes per known model; new models must be added here so collection
# creation and search stay consistent.
_VECTOR_SIZES = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

_lock = threading.Lock()
_fastembed_model = None


def provider() -> str:
    """"fastembed" (default) or "openai" (legacy, requires the openai pkg)."""
    value = (os.environ.get("EMBEDDINGS_PROVIDER") or "fastembed").strip().lower()
    return value if value in ("fastembed", "openai") else "fastembed"


def model_name() -> str:
    if provider() == "openai":
        return os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return os.environ.get("FASTEMBED_MODEL", DEFAULT_FASTEMBED_MODEL)


def vector_size() -> int:
    return _VECTOR_SIZES.get(model_name(), 384 if provider() == "fastembed" else 1536)


def _cache_dir() -> Optional[str]:
    """Model cache resolution: explicit env → baked image dir → fastembed default."""
    explicit = (os.environ.get("FASTEMBED_CACHE_DIR") or "").strip()
    if explicit:
        return explicit
    baked = "/opt/fastembed-cache"
    if os.path.isdir(baked):
        return baked
    return None


def _get_fastembed():
    global _fastembed_model
    if _fastembed_model is None:
        with _lock:
            if _fastembed_model is None:
                from fastembed import TextEmbedding

                kwargs = {}
                cache = _cache_dir()
                if cache:
                    kwargs["cache_dir"] = cache
                logger.info(
                    "Loading fastembed model %s (cache=%s)", model_name(), cache or "default"
                )
                _fastembed_model = TextEmbedding(model_name=model_name(), **kwargs)
    return _fastembed_model


def _embed_fastembed(texts: list[str]) -> list[list[float]]:
    model = _get_fastembed()
    vectors = [vec.tolist() for vec in model.embed(texts)]
    logger.debug("fastembed embedded %d text(s)", len(vectors))
    return vectors


def _embed_openai(texts: list[str]) -> list[list[float]]:
    from app.services.clients import get_openai_client
    from app.services.llm_usage import record_usage

    model = model_name()
    client = get_openai_client()
    r = client.embeddings.create(input=texts, model=model)
    record_usage(model=model, purpose="embedding", usage=getattr(r, "usage", None))
    return [d.embedding for d in r.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts with the configured provider."""
    if not texts:
        return []
    if provider() == "openai":
        return _embed_openai(texts)
    return _embed_fastembed(texts)


def reset_for_tests() -> None:
    global _fastembed_model
    _fastembed_model = None
