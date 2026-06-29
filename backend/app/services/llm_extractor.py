"""
Path A: Extract text from PDF/DOCX, call LLM to get structured client profile + alerts,
for writing to Postgres (clients + alerts tables).
Extraction results are cached by content hash to avoid repeated LLM calls for same document text.
"""
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import pymupdf
from docx import Document as DocxDocument

from app.services.cache import EXTRACT_TTL, get as cache_get, set_ as cache_set
from app.services.prompts import EXTRACTION_SYSTEM, PROMPT_VERSION

logger = logging.getLogger("jarvis.ingest")


def extract_text_from_file(file_path: Path) -> str:
    """Extract plain text from a PDF or DOCX file."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        doc = pymupdf.open(path)
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        text = "\n\n".join(parts).strip()
        logger.info("[ingest] PDF extracted: %s → %d chars, %d pages", path.name, len(text), len(parts))
        return text
    if suffix == ".docx":
        doc = DocxDocument(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs).strip()
        logger.info("[ingest] DOCX extracted: %s → %d chars, %d paragraphs", path.name, len(text), len(paragraphs))
        return text
    raise ValueError(f"Unsupported file type: {suffix}")


# EXTRACTION_SYSTEM lives in app.services.prompts (versioned via PROMPT_VERSION)


def _call_llm_openai(text: str, model: str) -> str:
    from app.services.clients import get_openai_client
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


def extract_structured(file_path: Path) -> dict[str, Any]:
    """
    Extract text from file, call LLM, return { "client": {...}, "alerts": [...] }.
    Results cached by content hash (EXTRACT_TTL) to reduce LLM calls for same/similar documents.
    Raises on missing env or parse/LLM errors.
    """
    text = extract_text_from_file(file_path)
    if not text or len(text) < 50:
        logger.warning("[ingest] Document too short (<50 chars), skipping LLM; using placeholder client")
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
    # Log extracted summary (no huge payloads)
    name = (client.get("full_name") or "Unknown Client").strip() or "Unknown Client"
    logger.info(
        "[ingest] LLM extracted → client: %s (risk=%s, assets=%s, review=%s); alerts: %d",
        name,
        client.get("risk_score"),
        client.get("total_assets"),
        client.get("last_review_date"),
        len(alerts),
    )
    for i, a in enumerate(alerts[:10]):
        logger.info(
            "[ingest]   alert[%d] %s | %s | %s | %s",
            i,
            a.get("trigger_date"),
            a.get("type"),
            a.get("priority"),
            (a.get("title") or "")[:50],
        )
    if len(alerts) > 10:
        logger.info("[ingest]   ... and %d more alerts", len(alerts) - 10)
    result = {"client": client, "alerts": alerts, "raw_text": text}
    cache_set(cache_key, {"client": client, "alerts": alerts}, EXTRACT_TTL)
    return result
