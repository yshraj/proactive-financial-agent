"""
Path A: Extract text from PDF/DOCX, call LLM to get structured client profile + alerts,
for writing to Postgres (clients + alerts tables).
Extraction results are cached by content hash to avoid repeated LLM calls for same document text.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

import pymupdf
from docx import Document as DocxDocument

from app.services.cache import EXTRACT_TTL, get_scoped as cache_get, set_scoped as cache_set
from app.services.prompts import EXTRACTION_SYSTEM, PROMPT_VERSION

logger = logging.getLogger("jarvis.ingest")

# Extraction caps: bound CPU/memory even for pathological documents.
MAX_PDF_PAGES = 500
MAX_EXTRACT_CHARS = 500_000


def extract_text_from_bytes(content: bytes, ext: str, display_name: str = "document") -> str:
    """Extract plain text from PDF or DOCX bytes (page/char capped)."""
    ext = ext.lower()
    if ext == ".pdf":
        doc = pymupdf.open(stream=content, filetype="pdf")
        parts = []
        try:
            for index, page in enumerate(doc):
                if index >= MAX_PDF_PAGES:
                    logger.warning("[ingest] PDF page cap hit (%d): %s", MAX_PDF_PAGES, display_name)
                    break
                parts.append(page.get_text())
                if sum(len(p) for p in parts) > MAX_EXTRACT_CHARS:
                    break
        finally:
            doc.close()
        text = "\n\n".join(parts).strip()[:MAX_EXTRACT_CHARS]
        logger.info("[ingest] PDF extracted: %s → %d chars, %d pages", display_name, len(text), len(parts))
        return text
    if ext == ".docx":
        import io

        from app.services.safety import validate_docx_zip

        ok, reason = validate_docx_zip(content)
        if not ok:
            raise ValueError(f"DOCX rejected: {reason}")
        doc = DocxDocument(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs).strip()[:MAX_EXTRACT_CHARS]
        logger.info("[ingest] DOCX extracted: %s → %d chars, %d paragraphs", display_name, len(text), len(paragraphs))
        return text
    if ext in (".txt", ".md"):
        # utf-8-sig tolerates a BOM; upstream validation already rejected
        # binaries masquerading as text.
        return content.decode("utf-8-sig", errors="replace")[:MAX_EXTRACT_CHARS]
    raise ValueError(f"Unsupported file type: {ext}")


# EXTRACTION_SYSTEM lives in app.services.prompts (versioned via PROMPT_VERSION)


def _call_llm(text: str) -> tuple[str, str, str, dict | None]:
    """Structured extraction via the model gateway (long-context free models
    first — see the "extraction" route in services/model_gateway.py).

    Returns (raw_json_text, provider/model label used, finish_reason, usage).

    ``reasoning_effort="none"`` disables Gemini 2.5's "thinking" pass, which
    otherwise spends hidden tokens out of the *same* completion budget before
    any visible content — on long documents that can consume most of the
    budget and truncate the visible JSON (finish_reason="length"), a
    malformed-JSON failure that looks unrelated to token limits unless you
    check usage. Extraction is a deterministic formatting task with no
    reasoning benefit, so disabling it is strictly better: faster, cheaper,
    and reliable regardless of document length. (Ignored by non-Gemini
    providers in the fallback chain — see model_gateway.chat.) max_tokens is
    kept generous as a second line of defence.
    """
    from app.services.llm import complete_ex

    result = complete_ex(
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": f"Document text:\n\n{text[:100000]}"},
        ],
        max_tokens=8192,
        temperature=0,
        purpose="extraction",
        response_format={"type": "json_object"},
        reasoning_effort="none",
    )
    return result.content, result.label, result.finish_reason, result.usage


def _strip_json_comments(s: str) -> str:
    """Remove ``//`` and ``/* */`` comments outside string literals."""
    out: list[str] = []
    i, n = 0, len(s)
    in_str = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_commas(s: str) -> str:
    """Remove commas that directly precede ``}`` or ``]`` outside strings."""
    out: list[str] = []
    i, n = 0, len(s)
    in_str = False
    while i < n:
        c = s[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j < n and s[j] in "}]":
                i += 1  # drop the trailing comma; keep the whitespace/closer
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse LLM response into { client, alerts }.

    Tolerates a markdown code fence, and repairs the JSON-mode syntax slips
    providers still make — trailing commas and inline comments (observed in
    production: gemini-2.5-flash emitting a trailing comma mid-object, which
    is deterministic at temperature 0 and so failed every retry of the same
    document). Only the decode error is ever logged, never the payload.
    """
    s = raw.strip()
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    try:
        return json.loads(s)
    except json.JSONDecodeError as err:
        repaired = _strip_trailing_commas(_strip_json_comments(s))
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            raise err from None  # repair didn't help; report the original position
        logger.warning("[ingest] LLM JSON needed syntax repair: %s", err)
        return data


def extract_structured_from_text(text: str) -> dict[str, Any]:
    """
    Run LLM structured extraction over document/transcript text, returning
    ``{"client": {...}, "alerts": [...], "raw_text": ...}``. Results are cached
    by content hash (EXTRACT_TTL) to reduce LLM calls for identical documents.
    """
    text = text or ""
    if len(text) < 50:
        logger.warning("[ingest] Text too short (<50 chars), skipping LLM; using placeholder client")
        return {"client": {"full_name": "Unknown Client", "raw_profile_json": {}}, "alerts": [], "raw_text": text}

    content_for_hash = text[:100000]
    content_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()[:24]
    cache_key = f"extract:{PROMPT_VERSION}:{content_hash}"
    cached = cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        logger.info("[ingest] Using cached extraction for content hash %s", content_hash)
        return {"client": cached.get("client") or {}, "alerts": cached.get("alerts") or [], "raw_text": text}

    logger.info("[ingest] Calling LLM gateway for structured extraction...")
    raw, model_label, finish_reason, usage = _call_llm(text)
    logger.info("[ingest] Extraction answered by %s (finish_reason=%s, usage=%s)",
                model_label, finish_reason or "unknown", usage or {})

    try:
        data = _parse_llm_json(raw)
    except json.JSONDecodeError:
        # Diagnostic-only, never the payload (PII policy): finish_reason
        # "length" + a completion_tokens count close to max_tokens means the
        # model was cut off mid-JSON — raise max_tokens, don't chase a JSON
        # repair bug. Any other finish_reason points at a genuine malformed
        # response worth reporting upstream.
        logger.error(
            "[ingest] LLM JSON parse failed — model=%s finish_reason=%s usage=%s raw_len=%d "
            "(finish_reason='length' means the response was truncated, likely by max_tokens; "
            "see model_gateway 'extraction' purpose config)",
            model_label, finish_reason or "unknown", usage or {}, len(raw),
        )
        raise
    client = data.get("client") or {}
    alerts = data.get("alerts")
    if not isinstance(alerts, list):
        alerts = []
    # Log a structural summary only — never client names, financial figures,
    # or alert titles (PII policy in app.logging_config).
    logger.info(
        "[ingest] LLM extracted → client resolved (named=%s, risk=%s); alerts: %d",
        bool((client.get("full_name") or "").strip()),
        client.get("risk_score"),
        len(alerts),
    )
    for i, a in enumerate(alerts[:10]):
        logger.info(
            "[ingest]   alert[%d] %s | %s | %s",
            i,
            a.get("trigger_date"),
            a.get("type"),
            a.get("priority"),
        )
    if len(alerts) > 10:
        logger.info("[ingest]   ... and %d more alerts", len(alerts) - 10)
    result = {"client": client, "alerts": alerts, "raw_text": text}
    cache_set(cache_key, {"client": client, "alerts": alerts}, EXTRACT_TTL)
    return result
