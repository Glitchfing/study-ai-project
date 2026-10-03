from __future__ import annotations

import json
from typing import Any

from ai_generation import generate_structured_json, has_llm_support

DIAGRAM_EXPLANATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "caption": {"type": "string"},
        "explanation": {"type": "string"},
        "workflow_description": {"type": "string"},
        "connected_topics": {"type": "array", "items": {"type": "string"}},
        "exam_use": {"type": "string"},
    },
    "required": ["caption", "explanation", "workflow_description", "connected_topics", "exam_use"],
}


def generate_workflow_description(diagram: dict[str, Any], section: dict[str, Any] | None = None) -> str:
    title = (section or {}).get("title") or "the related topic"
    caption = diagram.get("caption") or diagram.get("context_text") or "the diagram"
    return f"Use {caption} to trace the flow of {title}: identify the starting point, components, relationship arrows, and final output."


def _fallback_explanation(diagram: dict[str, Any], section: dict[str, Any] | None = None) -> dict[str, Any]:
    caption = diagram.get("caption") or f"Diagram from page {diagram.get('page_number', '')}".strip()
    return {
        "caption": caption,
        "explanation": f"This visual supports {(section or {}).get('title', 'the topic')} by showing structure, relationships, or process flow.",
        "workflow_description": generate_workflow_description(diagram, section),
        "connected_topics": (section or {}).get("topics") or [],
        "exam_use": "In an exam answer, redraw or describe the diagram before explaining the concept in words.",
    }


def explain_diagram(diagram: dict[str, Any], section: dict[str, Any] | None = None) -> dict[str, Any]:
    if not has_llm_support():
        return _fallback_explanation(diagram, section)
    system_prompt = (
        "You explain educational diagrams for study notes. Connect the diagram to the surrounding concept, workflow, "
        "architecture, and exam use. Return JSON only."
    )
    user_prompt = (
        f"Diagram metadata:\n{json.dumps(diagram, ensure_ascii=True)}\n\n"
        f"Related section:\n{json.dumps(section or {}, ensure_ascii=True)}"
    )
    try:
        return generate_structured_json(system_prompt, user_prompt, "diagram_explanation", DIAGRAM_EXPLANATION_SCHEMA)
    except Exception:
        return _fallback_explanation(diagram, section)


def connect_diagram_to_notes(diagram: dict[str, Any], section: dict[str, Any]) -> dict[str, Any]:
    explanation = explain_diagram(diagram, section)
    diagram["caption"] = diagram.get("caption") or explanation["caption"]
    diagram["explanation"] = explanation["explanation"]
    diagram["workflow_description"] = explanation["workflow_description"]
    diagram["connected_topics"] = explanation["connected_topics"]
    diagram["exam_use"] = explanation["exam_use"]
    diagram["section_id"] = section.get("section_id")
    return diagram
