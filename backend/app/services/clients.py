"""
Lazy singleton external clients.

Previously OpenAI and Qdrant clients were constructed on every request, adding
latency and connection churn. These helpers create them once per process.
"""
from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_openai_client = None
_qdrant_client = None


def get_openai_client():
    """Legacy OpenAI SDK client, used only when EMBEDDINGS_PROVIDER=openai.

    The openai package is no longer a core dependency (completions go
    through the httpx gateway; embeddings default to local fastembed) —
    deployments that pin the legacy provider must `pip install openai`.
    """
    global _openai_client
    if _openai_client is None:
        with _lock:
            if _openai_client is None:
                from openai import OpenAI

                # Bounded for Lambda: worst case = timeout * (1 + retries).
                # Defaults (60s, 1 retry -> 120s) fit inside both the API
                # function's 180s cap and the worker's per-job budget; the
                # SDK's own default of 2 retries would exactly exhaust the
                # API timeout on a hung call.
                timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))
                max_retries = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
                _openai_client = OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                    timeout=timeout,
                    max_retries=max_retries,
                )
    return _openai_client


def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        with _lock:
            if _qdrant_client is None:
                from qdrant_client import QdrantClient

                url = os.environ.get("QDRANT_URL")
                if not url:
                    raise RuntimeError("QDRANT_URL is not set")
                _qdrant_client = QdrantClient(
                    url=url, api_key=os.environ.get("QDRANT_API_KEY") or None
                )
    return _qdrant_client
