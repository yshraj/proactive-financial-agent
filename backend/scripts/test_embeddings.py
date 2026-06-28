"""
Test embeddings API and optionally Qdrant (upsert one point, search).
Run from repo root: python backend/scripts/test_embeddings.py
Requires: pip install openai qdrant-client python-dotenv
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION = os.getenv("QDRANT_COLLECTION", "client_memory")

TEST_TEXT = "Client mentioned retirement at 58 and concern about market volatility."


def get_embedding_openai(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    r = client.embeddings.create(input=[text], model=MODEL)
    return r.data[0].embedding


def test_embeddings_only():
    """Only call embeddings API and print dimension."""
    if PROVIDER != "openai" or not OPENAI_API_KEY:
        print("ERR EMBEDDING_PROVIDER=openai and OPENAI_API_KEY required for this script.")
        return False, None
    try:
        vec = get_embedding_openai(TEST_TEXT)
        print(f"OK  Embeddings ({MODEL}): dimension={len(vec)}")
        return True, vec
    except Exception as e:
        print(f"ERR Embeddings: {e}")
        return False, None


def test_qdrant_roundtrip(vec: list[float]):
    """Upsert one point and search to verify Qdrant + embedding dimension."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, PointIdsList

        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        pid = uuid.uuid4()
        client.upsert(
            collection_name=COLLECTION,
            points=[PointStruct(id=pid, vector=vec, payload={"content": TEST_TEXT, "doc_type": "test"})],
            wait=True,
        )
        # Use query_points (QdrantBase API); get a few hits in case other points exist
        resp = client.query_points(collection_name=COLLECTION, query=vec, limit=5)
        hits = getattr(resp, "points", resp) if not isinstance(resp, list) else resp
        client.delete(collection_name=COLLECTION, points_selector=PointIdsList(points=[pid]))
        # Success if our point appears in results (by id or by payload content)
        found = any(
            str(getattr(h, "id", None)) == str(pid)
            or (isinstance(p := getattr(h, "payload", None), dict) and p.get("content") == TEST_TEXT)
            for h in (hits or [])
        )
        if found:
            print("OK  Qdrant roundtrip: upsert + search for test point succeeded.")
            return True
        print("WARN Qdrant roundtrip: search did not return the test point.")
        return False
    except Exception as e:
        print(f"ERR Qdrant roundtrip: {e}")
        return False


def main():
    print("Testing embeddings...")
    ok, vec = test_embeddings_only()
    if not ok:
        sys.exit(1)
    if vec and QDRANT_URL:
        print("Testing embeddings + Qdrant...")
        test_qdrant_roundtrip(vec)
    sys.exit(0)


if __name__ == "__main__":
    main()
