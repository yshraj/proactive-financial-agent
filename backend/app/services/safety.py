"""
Input sanitization and defensive helpers for security-sensitive paths.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("jarvis.safety")

# Common prompt-injection phrases to strip from untrusted document text before RAG indexing/retrieval.
# Allows optional filler ("the", "all") between the verb and the target so
# variants like "disregard the above" / "ignore all the previous rules" match.
_INJECTION_PATTERNS = re.compile(
    r"(?i)("
    r"ignore (all |any |the )*(previous|prior|above|preceding)( (instructions|rules|prompts|text|context))?"
    r"|disregard (all |any |the )*(previous|prior|above|preceding|instructions|rules)"
    r"|forget (all |any |the |everything )*(previous|prior|above|instructions|rules)"
    r"|you are now"
    r"|act as (an? )?(unrestricted|jailbroken|dan)"
    r"|system:\s*"
    r"|<\s*/?\s*(system|instruction|prompt)\s*>"
    r")",
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


# DOCX (zip) decompression-bomb guards: a 20MB upload must not expand into
# gigabytes of XML when python-docx parses it.
_MAX_ZIP_ENTRIES = 2000
_MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024  # 200 MB total
_MAX_ZIP_RATIO = 100.0  # per-entry compression ratio


def validate_docx_zip(content: bytes) -> tuple[bool, str]:
    """Reject zip bombs before DOCX parsing. Returns (ok, reason)."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES:
                return False, "Archive contains too many entries."
            total_uncompressed = 0
            for info in infos:
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_ZIP_UNCOMPRESSED:
                    return False, "Archive expands beyond the allowed size."
                if info.compress_size > 0 and info.file_size / info.compress_size > _MAX_ZIP_RATIO:
                    return False, "Archive compression ratio is suspicious."
    except zipfile.BadZipFile:
        return False, "File is not a valid DOCX archive."
    except Exception:
        return False, "File could not be inspected."
    return True, ""


def public_error_message(context: str, exc: Exception | None = None) -> str:
    """Return a safe client-facing error string; log full detail server-side."""
    if exc is not None:
        logger.exception("[%s] %s", context, exc)
    messages = {
        "postgres_clear": "Failed to clear database records. Check server logs.",
        "qdrant_clear": "Failed to clear vector index. Check server logs.",
        "ingest_extraction": "Document extraction failed. The file was stored but could not be processed.",
        "ingest_vector": "Document indexing failed. The file was stored but search may be incomplete.",
        "ingest_storage": "Document storage failed. Please try the upload again.",
        "internal": "An unexpected error occurred. The team has been notified.",
    }
    return messages.get(context, "An internal error occurred. Check server logs.")
