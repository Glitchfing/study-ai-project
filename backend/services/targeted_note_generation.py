from __future__ import annotations

from datetime import datetime
from typing import Any

from note_generation import (
    _aggregate_cornell,
    _aggregate_outline,
    _aggregate_mindmap,
    _aggregate_chart,
    _aggregate_sentence,
    _attach_section_questions,
)
from services.llm_orchestrator import run_targeted_note_pipeline


def generate_targeted_note_package(
    context: str,
    topic: str,
    source_metadata: dict[str, Any],
    preferences: dict[str, Any] | None = None,
    extracted_diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Generate a complete, multi-format note package focused on a single topic,
    synthesized from retrieved RAG context snippets.
    """
    clean_topic = topic.strip() or "Targeted Topic"
    pref = dict(preferences or {})
    pref.setdefault("note_depth", "deep")
    pref.setdefault("preferred_format", "cornell")
    pref.setdefault("exam_focus", True)
    pref.setdefault("include_examples", True)
    pref.setdefault("include_diagrams", True)

    filename = source_metadata.get("filename") or "Document"
    pages = source_metadata.get("pages") or []

    pipeline_result = run_targeted_note_pipeline(
        context=context,
        topic=clean_topic,
        source_metadata=source_metadata,
        diagrams=extracted_diagrams or [],
        preferences=pref,
        quiz_limit=max(6, min(15, len(pages) * 3 if pages else 8)),
    )

    intelligence = pipeline_result.get("document_intelligence") or {}
    sections = pipeline_result.get("sections") or []
    questions = pipeline_result.get("questions") or []
    _attach_section_questions(sections, questions)

    title = f"{clean_topic} — Targeted Study"
    summary = intelligence.get("document_summary") or f"Focused notes on {clean_topic}."

    package = {
        "document_title": title,
        "source_filename": filename,
        "source_files": [{"filename": filename, "page_count": len(pages)}],
        "total_uploaded_files": 1,
        "total_sections": len(sections),
        "sections": sections,
        "notes": {
            "cornell": _aggregate_cornell(sections, title),
            "outline": _aggregate_outline(sections, title),
            "mindmap": _aggregate_mindmap(sections, title),
            "chart": _aggregate_chart(sections, title),
            "sentence": _aggregate_sentence(sections, title, summary),
        },
        "diagrams": [diagram for s in sections for diagram in s.get("diagrams", [])],
        "questions": questions,
        "global_summary": summary,
        "document_intelligence": intelligence,
        "topic_map": intelligence,
        "difficulty_level": "intermediate",
        "requested_topic": clean_topic,
        "generation_mode": "targeted",
        "retrieval": pipeline_result.get("retrieval", {}),
        "pipeline_diagnostics": {
            "pipeline": [
                "targeted_query_embedding",
                "qdrant_document_filtering",
                "deduplication_and_sorting",
                "focused_context_assembly",
                "targeted_note_generation",
                "targeted_quiz_generation",
            ],
            "mode": "targeted_topic",
            "requested_topic": clean_topic,
            "source_pages": pages,
            "section_count": len(sections),
        },
        "preferences": pref,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    return package
