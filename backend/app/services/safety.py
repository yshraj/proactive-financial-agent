"""
Input sanitization and defensive helpers for security-sensitive paths.
"""
from __future__ import annotations

import codecs
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


def _normalize_ws(text: str) -> str:
    """Lowercase and collapse whitespace for tolerant substring matching."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


# Distinctive opening of the shared assistant persona (see services/prompts.py
# JARVIS_PERSONA). Any model output that echoes it verbatim is disclosing its
# system prompt — a prompt-injection symptom the agent reviewer treats as a
# hard failure. Kept in sync with the persona by a unit test.
_PROMPT_ECHO_CANARY = "you are jarvis, an ai copilot for uk independent financial advisers"


def contains_prompt_echo(text: str) -> bool:
    """True when model output appears to quote the system persona verbatim.

    Deterministic backstop for the review node: even if the drafting model is
    coaxed into 'reiterating its instructions' by a prompt-injection attempt,
    this catches the verbatim echo so the draft is failed and revised.
    """
    if not text:
        return False
    return _PROMPT_ECHO_CANARY in _normalize_ws(text)


def is_plausible_text(content: bytes) -> bool:
    """True when bytes look like a genuine UTF-8 text document.

    Text formats (.md/.txt) have no magic number, so the equivalent check is:
    decodes as UTF-8 (BOM tolerated) and contains no NUL bytes — which rejects
    binaries masquerading under a text extension.
    """
    if not content:
        return False
    sample = content[:64 * 1024]
    if b"\x00" in sample:
        return False
    # Incremental decode: when the sample truncates the file mid-way through a
    # multi-byte sequence, final=False buffers the incomplete tail instead of
    # raising; genuinely invalid bytes still fail.
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        decoder.decode(sample, final=len(content) <= len(sample))
    except UnicodeDecodeError:
        return False
    return True


def validate_file_magic(content: bytes, ext: str) -> bool:
    """Verify file content matches its extension (magic bytes, or a UTF-8
    plausibility check for text formats that have none)."""
    if not content:
        return False
    ext = ext.lower()
    if ext == ".pdf":
        return content[:5] == b"%PDF-"
    if ext == ".docx":
        # DOCX is a ZIP archive (PK\x03\x04)
        return content[:4] == b"PK\x03\x04"
    if ext in (".md", ".txt"):
        return is_plausible_text(content)
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
    """Return a safe client-facing error string; log full detail server-side.

    Never put ``str(exc)`` (SQL, provider errors, hostnames, file paths) into
    anything a client can see — pass the exception here so it lands in the
    server logs, and hand the caller a fixed, friendly string instead.
    """
    if exc is not None:
        logger.exception("[%s] %s", context, exc)
    messages = {
        "postgres_clear": "We couldn't clear your workspace data. Please try again.",
        "qdrant_clear": "We couldn't clear the search index. Please try again.",
        "ingest_extraction": "Document extraction failed. The file was stored but could not be processed.",
        "ingest_vector": (
            "The document was stored, but search indexing is temporarily "
            "unavailable. Try re-uploading it later."
        ),
        "ingest_persist": (
            "The document was stored, but we couldn't save the extracted "
            "details. Please try the upload again."
        ),
        "ingest_storage": "Document storage failed. Please try the upload again.",
        "ai_unavailable": "We couldn't generate AI results right now. Please try again in a few minutes.",
        "search_unavailable": "Search is temporarily unavailable. Please try again shortly.",
        "job_failed": "Processing failed after several attempts. Please try uploading the document again.",
        "load_sample_data": "Loading sample data failed. Please try again.",
        "internal": "An unexpected error occurred. The team has been notified.",
    }
    return messages.get(context, "Something went wrong. Please try again.")


# ---------------------------------------------------------------------------
# Structured error envelope (attached to every error response by the handlers
# in app.main): {"error": {"code", "message", "retryable"}}. The legacy
# "detail" key is preserved alongside for existing clients and tests.
# ---------------------------------------------------------------------------

_ERROR_CODE_BY_STATUS = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "upload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_unavailable",
    503: "service_unavailable",
    504: "timeout",
}

_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def error_envelope(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    retryable: bool | None = None,
) -> dict:
    """Build the machine-readable error object for an error response."""
    return {
        "code": code or _ERROR_CODE_BY_STATUS.get(status_code, "error"),
        "message": message,
        "retryable": (
            retryable if retryable is not None else status_code in _RETRYABLE_STATUSES
        ),
    }


def detail_to_message(detail: object, status_code: int) -> str:
    """Extract a human-readable message from an HTTPException detail."""
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message:
            return message
    if status_code == 422:
        return "Some fields are invalid. Please review and try again."
    return "Something went wrong. Please try again."
