"""
Document storage: private Supabase Storage bucket with org-prefixed keys.

Render's filesystem is ephemeral — anything written to backend/uploads/ is lost
on every deploy — so originals live in Supabase Storage (RFC decision D6):

- bucket: STORAGE_BUCKET (default "documents"), private
- key: "{org_id}/{document_id}{ext}" — the org prefix keeps tenant files
  physically separated and makes per-org DSAR/export straightforward
- auth: SUPABASE_SERVICE_ROLE_KEY (server-side only, never shipped to browsers)

When Supabase Storage is not configured (local dev without a project), files
fall back to backend/uploads/{org_id}/ so the ingestion pipeline still works;
the readiness report and posture surface that state.

Stored references are written to ingested_documents.file_path as
"storage:{bucket}/{key}" or "uploads/{org_id}/{name}" (legacy rows keep
"uploads/{name}" and remain readable).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.storage")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = BACKEND_ROOT / "uploads"

_bucket_checked = False


def storage_bucket() -> str:
    return (os.environ.get("STORAGE_BUCKET") or "documents").strip()


def _service_key() -> Optional[str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return key.strip() if key else None


def _storage_base_url() -> Optional[str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    return f"{url}/storage/v1" if url else None


def supabase_storage_enabled() -> bool:
    return bool(_storage_base_url() and _service_key())


def _headers() -> dict:
    key = _service_key()
    return {"Authorization": f"Bearer {key}", "apikey": key or ""}


def _ensure_bucket() -> None:
    """Create the private bucket if missing (idempotent, checked once)."""
    global _bucket_checked
    if _bucket_checked:
        return
    import httpx

    base = _storage_base_url()
    bucket = storage_bucket()
    try:
        resp = httpx.post(
            f"{base}/bucket",
            headers=_headers(),
            json={"id": bucket, "name": bucket, "public": False},
            timeout=15,
        )
        if resp.status_code not in (200, 201, 400, 409):
            logger.warning("Bucket ensure returned %s: %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("Bucket ensure failed for %s", bucket)
    _bucket_checked = True


def object_key(org_id: str, document_id: str, ext: str) -> str:
    return f"{org_id}/{document_id}{ext}"


def save_document(org_id: str, document_id: str, ext: str, content: bytes) -> str:
    """Persist an uploaded document; returns the file_path reference to store."""
    if supabase_storage_enabled():
        import httpx

        _ensure_bucket()
        key = object_key(org_id, document_id, ext)
        resp = httpx.post(
            f"{_storage_base_url()}/object/{storage_bucket()}/{key}",
            headers={**_headers(), "Content-Type": "application/octet-stream", "x-upsert": "true"},
            content=content,
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Storage upload failed ({resp.status_code}): {resp.text[:200]}")
        return f"storage:{storage_bucket()}/{key}"

    # Local-dev fallback: org-prefixed path on disk.
    target_dir = UPLOADS_DIR / org_id
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / f"{document_id}{ext}"
    local_path.write_bytes(content)
    return f"uploads/{org_id}/{document_id}{ext}"


def fetch_document(file_path: str) -> bytes:
    """Load a stored document by its file_path reference."""
    if file_path.startswith("storage:"):
        import httpx

        ref = file_path[len("storage:"):]
        bucket, _, key = ref.partition("/")
        resp = httpx.get(
            f"{_storage_base_url()}/object/{bucket}/{key}", headers=_headers(), timeout=60
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Storage download failed ({resp.status_code}) for {key}")
        return resp.content
    if file_path.startswith("uploads/"):
        # Contain reads under uploads/; reject .. and symlink escapes.
        candidate = (BACKEND_ROOT / file_path).resolve()
        uploads_root = UPLOADS_DIR.resolve()
        if not (candidate == uploads_root or uploads_root in candidate.parents):
            raise ValueError(f"Unsafe file_path reference: {file_path!r}")
        return candidate.read_bytes()
    raise ValueError(f"Unsupported file_path reference: {file_path!r}")


def signed_url(file_path: str, expires_seconds: int = 300) -> Optional[str]:
    """Short-lived signed URL for a stored document (Supabase Storage only)."""
    if not file_path.startswith("storage:") or not supabase_storage_enabled():
        return None
    import httpx

    ref = file_path[len("storage:"):]
    bucket, _, key = ref.partition("/")
    resp = httpx.post(
        f"{_storage_base_url()}/object/sign/{bucket}/{key}",
        headers=_headers(),
        json={"expiresIn": expires_seconds},
        timeout=15,
    )
    if resp.status_code != 200:
        return None
    signed = (resp.json() or {}).get("signedURL")
    return f"{_storage_base_url()}{signed}" if signed else None


def delete_org_documents(org_id: str) -> None:
    """Best-effort removal of an org's stored files (data-reset flow)."""
    if supabase_storage_enabled():
        import httpx

        try:
            listing = httpx.post(
                f"{_storage_base_url()}/object/list/{storage_bucket()}",
                headers=_headers(),
                json={"prefix": f"{org_id}/", "limit": 1000},
                timeout=30,
            )
            names = [
                f"{org_id}/{item['name']}"
                for item in (listing.json() if listing.status_code == 200 else [])
                if isinstance(item, dict) and item.get("name")
            ]
            if names:
                httpx.request(
                    "DELETE",
                    f"{_storage_base_url()}/object/{storage_bucket()}",
                    headers=_headers(),
                    json={"prefixes": names},
                    timeout=60,
                )
        except Exception:
            logger.exception("Failed to delete stored documents for org %s", org_id)
        return
    local_dir = UPLOADS_DIR / org_id
    if local_dir.is_dir():
        for child in local_dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
