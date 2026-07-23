"""
Path A: Extract text from PDF/DOCX, call LLM to get structured client profile + alerts,
for writing to Postgres (clients + alerts tables).
Extraction results are cached by content hash to avoid repeated LLM calls for same document text.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
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


def _call_llm_openai(text: str, model: str) -> str:
    from app.services.clients import get_openai_client
    from app.services.llm_usage import record_usage
    client = get_openai_client()
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": f"Document text:\n\n{text[:100000]}"},
        ],
        max_tokens=4096,
        temperature=0,
    )
    record_usage(model=model, purpose="extraction", usage=getattr(r, "usage", None))
    return (r.choices[0].message.content or "").strip()


def _call_llm_gemini(text: str, model: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    m = genai.GenerativeModel(model)
    r = m.generate_content(
        f"{EXTRACTION_SYSTEM}\n\nDocument text:\n\n{text[:100000]}",
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return (r.text or "").strip()


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse LLM response into { client, alerts }. Tolerates markdown code fence."""
    s = raw.strip()
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    return json.loads(s)


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

    provider = (os.environ.get("LLM_PROVIDER") or "openai").lower()
    model = os.environ.get("LLM_MODEL") or ("gpt-4o" if provider == "openai" else "gemini-1.5-pro")
    logger.info("[ingest] Calling LLM (%s / %s) for structured extraction...", provider, model)
    if provider == "openai":
        raw = _call_llm_openai(text, model)
    elif provider == "gemini":
        raw = _call_llm_gemini(text, model)
    else:
        raise RuntimeError(f"LLM_PROVIDER must be openai or gemini, got {provider}")

    data = _parse_llm_json(raw)
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
