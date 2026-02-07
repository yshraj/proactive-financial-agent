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


# LLM output schema: client (for clients table) + alerts list (for alerts table)
# Tuned for UK adviser fact-finds and meeting notes (e.g. "CLIENT X: NAME", "Last Updated", "Next Review", RECOMMENDATIONS STATUS, UPCOMING ACTIONS).
EXTRACTION_SYSTEM = """You are a financial document analyst. Extract structured data from UK financial adviser documents: fact-finds, client profiles, and meeting notes.

Return a single JSON object with exactly two keys:
1. "client" – object with: full_name (string), retirement_target_age (int or null), risk_score (1-10 or null), total_assets (number or null), cash_savings (number or null), last_review_date (YYYY-MM-DD or null), raw_profile_json (object with any extra facts, or null).
2. "alerts" – array of objects. Each alert: trigger_date (YYYY-MM-DD), type (DEADLINE, OPPORTUNITY, COMPLIANCE, or FOLLOW_UP), priority (HIGH, MEDIUM, LOW), title (string), description (string), action_type (e.g. EMAIL_DRAFT), action_payload (object or null).

CLIENT NAME: Derive full_name from the document. Look for: "CLIENT 13: ALAN & LYNNE PARTRIDGE", "CLIENT PROFILE: DAVID & SARAH CHEN", "CLIENT FACT FIND - SARAH & MICHAEL THOMPSON", or "Client 1: David Chen" / "Client 2: Sarah Chen" (use "David & Sarah Chen"). Use the primary client/couple name; if only one person, use that name. If none found use "Unknown Client".

DATES: The document may use "Last Updated: 22/01/2026", "Next Review: 28/02/2027 (09:30, Office)", "Date Completed: 15th November 2024", "Review Date: November 2025". Convert all to YYYY-MM-DD. Accept: DD/MM/YYYY, DD/MM/YY, "15th November 2024", "January 2026", "Sept 2025". Use the latest year mentioned (e.g. Last Updated 22/01/2026 → 2026) for any year-only references. Set last_review_date from "Last Updated" or "Date Completed" or "Last Full Review: Jan 2026" when present.

FINANCIALS: total_assets from "Net Worth: £895,000" or "Total Assets: £1,405,270". cash_savings from "Joint Savings", "Easy Access Savings", or similar. retirement_target_age from "Alan retire age 65", "Retire David 58, Sarah 57", "Retire age 60 (both)" – use the main or earliest age mentioned.

ALERTS – extract all of the following when present:

1) NEXT REVIEW / SCHEDULED REVIEW – mandatory when present. "Next Review: 28/02/2027 (09:30, Office)" → trigger_date 2027-02-28, type DEADLINE, priority HIGH, title "Next review due", description "Scheduled review 09:30 Office". "Review Date: November 2025" → 2025-11-01 or 2025-11-30.

2) CLIENT AND SPOUSE/PARTNER DOBs – one alert per person with DOB. "DOB: 15/11/1965 (Age 60)" or "Date of Birth: 12th March 1978" → use the NEXT occurrence of that date in current/next year (e.g. 2026-11-15). type OPPORTUNITY, title "Client DOB – [Name] (DD Mon)", description "Annual check-in / birthday".

3) POLICY / COVER END DATES – "Life Cover: £200,000 (expires 2030, age 65)", "to 2045", "fixed until May 2026" → DEADLINE with trigger_date end of that period (e.g. 2030-12-31, 2026-05-31).

4) OTHER DEADLINES – mortgage "fixed until May 2026", "Remortgage planning (expires May 2026)", "Before Next Review (2026)" → DEADLINE with concrete YYYY-MM-DD where possible.

5) FOLLOW-UPS / WAITING ON CLIENT – create FOLLOW_UP alerts when the document implies the adviser is waiting on the client. Look in: "PENDING:" lists, "UPCOMING ACTIONS", "Before Next Review:", "At Next Review:", "RECOMMENDATIONS STATUS". Examples:
- "Alan to decide on pension contribution increase" / "Alan to decide on pension" → FOLLOW_UP, title "Waiting on client: pension decision", trigger_date 30 days after Last Updated if no date.
- "RE-QUOTE JAN 2025", "MUST COMPLETE 2026", "Revisit during 2026" → use that month/year (e.g. 2025-01-31, 2026-12-31, 2026-06-30).
- "Remortgage planning (expires May 2026)" – client decision needed → FOLLOW_UP or DEADLINE.
- "Priya authorised adviser to implement", "Anil procrastination – MUST COMPLETE 2026", "Wills update – STRONG PRIORITY", "LPAs – book solicitor" → FOLLOW_UP with a sensible trigger_date from context or 30 days after Last Updated.
- "Before Next Review (2026): Alan to decide... / Lynne GP follow-up" → one FOLLOW_UP per distinct action, trigger_date before Next Review date if given.
Use the document's "Last Updated" or "Next Review" to infer year; if no due date use 30 days from Last Updated (as YYYY-MM-DD). Extract every distinct follow-up or client-action item.

Rules: Output only valid JSON, no markdown or code fences. Convert all UK dates to YYYY-MM-DD. Extract at least 2–8 alerts for a typical fact-find; if you see Next Review and at least one DOB you must have at least 3 alerts. Strip £ and commas from numbers; use numeric values for total_assets and cash_savings."""


def _call_llm_openai(text: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": f"Document text:\n\n{text[:120000]}"},
        ],
        max_tokens=4096,
    )
    return (r.choices[0].message.content or "").strip()


def _call_llm_gemini(text: str, model: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    m = genai.GenerativeModel(model)
    r = m.generate_content(
        f"{EXTRACTION_SYSTEM}\n\nDocument text:\n\n{text[:120000]}",
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
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

    content_for_hash = text[:120000]
    content_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()[:24]
    prompt_version = hashlib.sha256(EXTRACTION_SYSTEM.encode("utf-8")).hexdigest()[:8]
    cache_key = f"extract:{prompt_version}:{content_hash}"
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
