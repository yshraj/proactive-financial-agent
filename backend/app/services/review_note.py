"""
Deterministic fallback for the client review note.

Used when the LLM is unavailable so the feature still produces a real,
file-ready note from structured data (parity with the digest fallback). Pure
and fully unit-testable.
"""
from __future__ import annotations


def fallback_review_note(
    *,
    client_name: str,
    profile_bits: str,
    open_items: list[str],
    today_iso: str,
) -> str:
    """Build a structured Consumer-Duty review note from data alone (no LLM)."""
    lines = [
        f"# Client review note — {client_name}",
        f"_Date: {today_iso}. Draft for adviser review — confirm before filing._",
        "",
        "## Summary",
        profile_bits or "No profile data on file.",
        "",
        "## Open items",
    ]
    if open_items:
        lines.extend(f"- {item}" for item in open_items)
    else:
        lines.append("- None outstanding.")
    lines.extend(
        [
            "",
            "## Consumer Duty",
            "- [ ] Ongoing service delivered and value assessed.",
            "- [ ] Client circumstances and objectives reviewed.",
            "- [ ] Vulnerability considerations checked.",
        ]
    )
    return "\n".join(lines)
