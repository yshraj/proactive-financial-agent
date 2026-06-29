"""
Adviser note templates.

Structured meeting-note skeletons (discovery, annual review, prospect,
suitability) that advisers can fill in. Pure (no DB/LLM): the catalog and the
markdown renderer are fully unit-testable.
"""
from __future__ import annotations

from typing import Any

NOTE_TEMPLATES: dict[str, dict[str, Any]] = {
    "discovery": {
        "name": "Discovery meeting",
        "sections": [
            "Goals and objectives",
            "Current financial position",
            "Attitude to risk and capacity for loss",
            "Dependants and protection needs",
            "Agreed next steps",
        ],
    },
    "annual_review": {
        "name": "Annual review",
        "sections": [
            "Changes since last review",
            "Performance vs objectives",
            "Cashflow and contributions update",
            "Suitability of current arrangements",
            "Consumer Duty: ongoing value and vulnerability check",
            "Actions and follow-ups",
        ],
    },
    "prospect": {
        "name": "Prospect meeting",
        "sections": [
            "Background and how they found us",
            "Needs and priorities",
            "Existing arrangements",
            "Fit and scope of advice",
            "Next steps",
        ],
    },
    "suitability": {
        "name": "Suitability discussion",
        "sections": [
            "Recommendation summary",
            "Why it is suitable (demands and needs)",
            "Risks and alternatives considered",
            "Costs and charges discussed",
            "Client understanding confirmed",
        ],
    },
}


def list_templates() -> list[dict[str, Any]]:
    """Return catalog metadata (id, name, section_count)."""
    return [
        {"id": tid, "name": t["name"], "section_count": len(t["sections"])}
        for tid, t in NOTE_TEMPLATES.items()
    ]


def render_template(template_id: str) -> str:
    """
    Render a template as a markdown skeleton with one heading per section.

    Raises:
        KeyError: if the template id is unknown.
    """
    template = NOTE_TEMPLATES[template_id]
    lines = [f"# {template['name']}", ""]
    for section in template["sections"]:
        lines.append(f"## {section}")
        lines.append("")
        lines.append("- ")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
