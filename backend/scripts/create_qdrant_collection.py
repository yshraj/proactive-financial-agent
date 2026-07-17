"""
Create the Qdrant collection for RAG (client_memory).
Uses vector size 1536 for OpenAI text-embedding-3-small.
Run from repo root: python backend/scripts/create_qdrant_collection.py
Requires: pip install qdrant-client python-dotenv
"""
import os
import sys
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# Collection name comes from QDRANT_COLLECTION so it stays consistent with the app.
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "client_memory")

# OpenAI text-embedding-3-small dimension
VECTOR_SIZE = 1536


def main():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

    collections = client.get_collections().collections
    if any(c.name == COLLECTION_NAME for c in collections):
        print(f"Collection '{COLLECTION_NAME}' already exists. Recreate? (y/N)")
        if input().strip().lower() != "y":
            print("Done. No change.")
            return
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing '{COLLECTION_NAME}'.")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    print(f"Created collection '{COLLECTION_NAME}' with vector size={VECTOR_SIZE}, distance=COSINE.")

    # Payload indexes: org_id is the tenant boundary (is_tenant optimisation
    # where supported), client_id the per-client filter.
    from qdrant_client.models import KeywordIndexParams

    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="org_id",
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
    except Exception:
        client.create_payload_index(
            collection_name=COLLECTION_NAME, field_name="org_id", field_schema="keyword"
        )
    client.create_payload_index(
        collection_name=COLLECTION_NAME, field_name="client_id", field_schema="keyword"
    )
    print("Payload indexes created: org_id (tenant), client_id.")
    print("Payload fields (for ingestion): content, org_id, client_id, doc_type, date, topics")


if __name__ == "__main__":
    main()
    sys.exit(0)
