from __future__ import annotations

import re
from datetime import datetime
from uuid import uuid4

REQUIRED_FORMATS = ("cornell", "outline", "mindmap", "chart", "sentence")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _trim(value, limit: int = 2000):
    if isinstance(value, str):
        return value.strip()[:limit]
    return value


def _dedupe(values):
    seen = set()
    output = []
    for value in values or []:
        normalized = str(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def _lower_keys(value):
    if isinstance(value, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_lower_keys(v) for v in value]
    return _trim(value)


def _word_count(value) -> int:
    if isinstance(value, str):
        return len(re.findall(r"\w+", value))
    if isinstance(value, dict):
        return sum(_word_count(v) for v in value.values())
    if isinstance(value, list):
        return sum(_word_count(v) for v in value)
    return 0


def _empty_format(format_type: str):
    if format_type == "cornell":
        return {"cue": [], "notes": "", "summary": ""}
    if format_type == "outline":
        return {"sections": []}
    if format_type == "mindmap":
        return {"root": "", "branches": []}
    if format_type == "chart":
        return {"columns": [], "rows": []}
    return ""


def normalize_generated_notes(package: dict, subject: str | None = None) -> dict:
    package = _lower_keys(package or {})
    note_id = str(uuid4())
    created_at = package.get("generated_at") or _now()
    title = package.get("document_title") or package.get("title") or "Untitled Note"
    raw_sections = [s for s in package.get("sections", []) if s and s.get("title")]
    tags = package.get("tags") or ([subject] if subject else [])

    note = {
        "id": note_id,
        "title": title,
        "subject": subject or package.get("subject") or "general",
        "difficulty": package.get("difficulty_level") or "",
        "tags": _dedupe(tags),
        "created_at": created_at,
        "updated_at": _now(),
        "total_sections": len(raw_sections),
        "estimated_read_time": 0,
        "progress": 0,
        "is_favorite": False,
        "last_opened": None,
    }

    sections = []
    section_content = []
    formats = []
    diagrams = []
    all_questions = {"mcq": [], "short": [], "long": []}

    for order_index, source_section in enumerate(raw_sections):
        section_id = str(uuid4())
        source_formats = source_section.get("notes") or source_section.get("formats") or {}
        section_text_source = {
            "title": source_section.get("title", ""),
            "topics": source_section.get("topics", []),
            "formats": source_formats,
        }
        word_count = _word_count(section_text_source)
        sections.append(
            {
                "id": section_id,
                "note_id": note_id,
                "title": source_section.get("title", ""),
                "order_index": order_index,
                "word_count": word_count,
            }
        )

        questions = source_section.get("questions") or []
        section_content.append(
            {
                "section_id": section_id,
                "topics": _dedupe(source_section.get("topics")),
                "explanation": _trim(source_section.get("explanation", "")),
                "key_points": _dedupe(source_section.get("key_points")),
                "definitions": _dedupe(source_section.get("definitions")),
                "examples": _dedupe(source_section.get("examples")),
                "use_cases": _dedupe(source_section.get("use_cases")),
                "important_notes": _dedupe(source_section.get("important_notes")),
                "why_this_matters": _trim(source_section.get("why_this_matters", "")),
                "common_mistakes": _dedupe(source_section.get("common_mistakes")),
                "test_yourself": _dedupe(source_section.get("test_yourself")),
                "questions": questions,
            }
        )

        for format_type in REQUIRED_FORMATS:
            formats.append(
                {
                    "section_id": section_id,
                    "format_type": format_type,
                    "content": source_formats.get(format_type, _empty_format(format_type)),
                }
            )

        for diagram in source_section.get("diagrams") or []:
            clean_diagram = dict(diagram)
            clean_diagram["section_id"] = section_id
            diagrams.append(clean_diagram)

        for question in questions:
            q_type = question.get("type", "short")
            if q_type == "mcq":
                all_questions["mcq"].append(question)
            elif q_type in {"long", "theory", "application"}:
                all_questions["long"].append(question)
            else:
                all_questions["short"].append(question)

    note["estimated_read_time"] = max(1, round(sum(s["word_count"] for s in sections) / 180)) if sections else 0

    return {
        "note": note,
        "sections": sections,
        "section_content": section_content,
        "formats": formats,
        "diagrams": diagrams,
        "quiz": {"note_id": note_id, **all_questions},
    }
