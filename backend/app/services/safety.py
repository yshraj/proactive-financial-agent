"""
Input sanitization and defensive helpers for security-sensitive paths.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("jarvis.safety")

# Common prompt-injection phrases to strip from untrusted document text before RAG indexing/retrieval.
_INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (all )?(previous|prior|above) (instructions|rules|prompts)"
    r"|disregard (all )?(previous|prior|above)"
    r"|you are now"
    r"|system:\s*"
    r"|<\s*/?\s*(system|instruction|prompt)\s*>)",
)

_MAX_USER_QUERY = 2000
_MAX_DRAFT_CONTEXT = 3000


def clamp_text(text: str, max_len: int) -> str:
    """Truncate user-controlled text to a safe maximum length."""
    if not text:
        return ""
    return text[:max_len]


def sanitize_user_query(text: str) -> str:
    """Clamp and wrap user query for LLM prompts."""
    return clamp_text((text or "").strip(), _MAX_USER_QUERY)


def sanitize_draft_context(text: str) -> str:
    return clamp_text((text or "").strip(), _MAX_DRAFT_CONTEXT)


def sanitize_rag_content(content: str) -> str:
    """Strip obvious injection patterns from retrieved document excerpts."""
    if not content:
        return ""
    cleaned = _INJECTION_PATTERNS.sub("[filtered]", content)
    return cleaned[:2000]


def validate_file_magic(content: bytes, ext: str) -> bool:
    """Verify file content matches expected extension via magic bytes."""
    if not content:
        return False
    ext = ext.lower()
    if ext == ".pdf":
        return content[:5] == b"%PDF-"
    if ext == ".docx":
        # DOCX is a ZIP archive (PK\x03\x04)
        return content[:4] == b"PK\x03\x04"
    return False


def public_error_message(context: str, exc: Exception | None = None) -> str:
    """Return a safe client-facing error string; log full detail server-side."""
    if exc is not None:
        logger.exception("[%s] %s", context, exc)
    messages = {
        "postgres_clear": "Failed to clear database records. Check server logs.",
        "qdrant_clear": "Failed to clear vector index. Check server logs.",
        "ingest_extraction": "Document extraction failed. The file was stored but could not be processed.",
        "ingest_vector": "Document indexing failed. The file was stored but search may be incomplete.",
    }
    return messages.get(context, "An internal error occurred. Check server logs.")
