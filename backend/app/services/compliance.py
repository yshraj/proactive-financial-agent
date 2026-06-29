"""
Deterministic compliance signal detection for UK adviser notes.

Pure, keyword/phrase-based scanning (no LLM/DB) so it is fully unit-testable and
fast. It surfaces *signals for adviser review* — it does not make determinations.
Taxonomy follows FCA FG21/1's four drivers of vulnerability and the four
Consumer Duty outcomes (PRIN 2A).
"""
from __future__ import annotations

import re
from typing import Any

# FCA FG21/1 four drivers of vulnerability -> indicative phrases.
VULNERABILITY_TAXONOMY: dict[str, list[str]] = {
    "Health": [
        "illness", "ill health", "diagnosis", "diagnosed", "cancer", "disability",
        "disabled", "mental health", "depression", "anxiety", "dementia",
        "terminal", "chronic", "long-term condition",
    ],
    "Life events": [
        "bereavement", "passed away", "death of", "divorce", "separation",
        "redundancy", "redundant", "job loss", "lost his job", "lost her job",
        "retirement", "caring for", "new baby",
    ],
    "Resilience": [
        "debt", "in arrears", "arrears", "struggling financially",
        "financial difficulty", "financial difficulties", "over-indebted",
        "low savings", "no savings", "can't afford", "cannot afford",
    ],
    "Capability": [
        "doesn't understand", "does not understand", "didn't understand",
        "confused", "not confident", "poor english", "language barrier",
        "numeracy", "literacy", "learning difficulty",
    ],
}

# Consumer Duty (PRIN 2A) four outcomes -> indicative phrases.
CONSUMER_DUTY_TAXONOMY: dict[str, list[str]] = {
    "Products and services": ["unsuitable", "not suitable", "wrong product", "mis-sold"],
    "Price and value": ["too expensive", "high fees", "poor value", "overcharged", "fees unclear"],
    "Consumer understanding": [
        "didn't understand", "did not understand", "doesn't understand",
        "unclear", "confusing", "not explained",
    ],
    "Consumer support": [
        "couldn't reach", "could not get through", "no response", "poor service",
        "complaint", "complained", "long wait",
    ],
}

# Trim each side of a match to this many characters for the returned excerpt.
_EXCERPT_PAD = 40


def _excerpt(text: str, start: int, end: int) -> str:
    lo = max(0, start - _EXCERPT_PAD)
    hi = min(len(text), end + _EXCERPT_PAD)
    snippet = text[lo:hi].strip()
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def _scan(text: str, taxonomy: dict[str, list[str]], key_name: str) -> list[dict[str, str]]:
    """Find the first occurrence of each phrase; return one hit per matched phrase."""
    lowered = text.lower()
    hits: list[dict[str, str]] = []
    for category, phrases in taxonomy.items():
        for phrase in phrases:
            # Word-boundary match so "ill" doesn't fire inside "skill".
            match = re.search(r"\b" + re.escape(phrase) + r"\b", lowered)
            if match:
                hits.append(
                    {
                        key_name: category,
                        "phrase": phrase,
                        "excerpt": _excerpt(text, match.start(), match.end()),
                    }
                )
    return hits


def scan_text(text: str) -> dict[str, Any]:
    """
    Scan free text for vulnerability drivers and Consumer Duty signals.

    Returns ``{vulnerability_signals, consumer_duty_flags, summary}`` where each
    signal is ``{category|outcome, phrase, excerpt}``. Empty/blank text yields no
    signals.
    """
    text = text or ""
    vulnerability_signals = _scan(text, VULNERABILITY_TAXONOMY, "category")
    consumer_duty_flags = _scan(text, CONSUMER_DUTY_TAXONOMY, "outcome")
    return {
        "vulnerability_signals": vulnerability_signals,
        "consumer_duty_flags": consumer_duty_flags,
        "summary": {
            "vulnerability_count": len(vulnerability_signals),
            "consumer_duty_count": len(consumer_duty_flags),
        },
    }
