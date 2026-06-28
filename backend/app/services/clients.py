"""
Lazy singleton external clients.

Previously OpenAI and Qdrant clients were constructed on every request, adding
latency and connection churn. These helpers create them once per process.
"""
import os
import threading

_lock = threading.Lock()
_openai_client = None
_qdrant_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        with _lock:
            if _openai_client is None:
                from openai import OpenAI

                _openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
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
