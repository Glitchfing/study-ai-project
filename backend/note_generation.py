from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from services.llm_orchestrator import run_multi_pass_pipeline


def _clean_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("â€¢", "-").replace("â—", "-").replace("â—¦", "-")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return "\n".join(line.strip() for line in normalized.splitlines()).strip()


def _title_from_filename(filename: str) -> str:
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()


def _split_pages(text: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"\[\[PAGE_(\d+)\]\]", text or ""))
    if not matches:
        return [{"page_number": 1, "text": text or ""}]
    pages = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_text = text[start:end].strip()
        if page_text:
            pages.append({"page_number": int(match.group(1)), "text": page_text})
    return pages or [{"page_number": 1, "text": text or ""}]


def _difficulty_from_text(text: str) -> str:
    words = len(re.findall(r"\w+", text or ""))
    if words < 900:
        return "beginner"
    if words < 4500:
        return "intermediate"
    return "advanced"


def _target_note_pages(source_page_count: int) -> dict[str, int]:
    """
    Adaptive output-size target.

    Very short documents need enough space to remain useful, while large
    documents should be compressed more strongly. This is document-agnostic
    and based only on source size.
    """
    pages = max(1, int(source_page_count or 1))

    if pages <= 5:
        ratio_min, ratio_max = 0.65, 1.00
    elif pages <= 20:
        # Typical target: 20 source pages -> about 11-15 note pages
        # depending on layout and diagram density.
        ratio_min, ratio_max = 0.60, 0.75
    elif pages <= 50:
        ratio_min, ratio_max = 0.45, 0.65
    else:
        # Large documents need stronger compression to remain practical.
        ratio_min, ratio_max = 0.38, 0.55

    return {
        "min": max(1, round(pages * ratio_min)),
        "max": max(2, round(pages * ratio_max)),
    }


def _dedupe(values: list[Any], limit: int | None = None) -> list[str]:
    seen = set()
    result = []
    for value in values or []:
        item = " ".join(str(value or "").split())
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if limit and len(result) >= limit:
            break
    return result


def _sentences(text: Any) -> list[str]:
    cleaned = _clean_text(str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned)
    return [item.strip(" -•●○\t") for item in re.split(r"(?<=[.!?])\s+", cleaned) if item.strip()]


def _shorten(text: Any, *, sentences: int = 2, chars: int = 320) -> str:
    candidates = _sentences(text)
    meaningful = [
        item
        for item in candidates
        if len(re.findall(r"[A-Za-z][A-Za-z0-9+-]*", item)) >= 5
    ]
    selected = (meaningful or candidates)[:sentences]
    value = " ".join(selected) if selected else " ".join(str(text or "").split())
    value = re.sub(r"\s+\d+\.$", ".", value).strip()
    if len(value) <= chars:
        return value
    trimmed = value[:chars].rsplit(" ", 1)[0].strip()
    return f"{trimmed}..." if trimmed else value[:chars]


def _topic_title(value: Any, fallback: str = "Topic") -> str:
    text = " ".join(str(value or fallback).replace("\n", " ").split())
    text = re.sub(r"^source file:\s*", "", text, flags=re.I)
    text = re.sub(r"^\d+(\.\d+)*\s*", "", text).strip(" :-")
    text = re.sub(r"\.(pdf|docx?|pptx?|txt)$", "", text, flags=re.I).strip()
    return text or fallback


def _cue_questions(title: str, content: Any) -> list[str]:
    topic = _topic_title(title)
    if not topic:
        return []
    questions = [f"What is {topic}?"]
    lowered = str(content or "").lower()
    if re.search(r"\b(step|cycle|process|flow|request|response|life)\b", lowered):
        questions.append(f"How does {topic} work?")
    elif re.search(r"\b(vs|versus|difference|compare|between)\b", lowered):
        questions.append(f"How is {topic} different from related concepts?")
    else:
        questions.append(f"Why is {topic} important?")
    return questions


def _meaning_sentence(title: str, content: Any) -> str:
    topic = _topic_title(title)
    text = _shorten(content, sentences=1, chars=220)
    if not text:
        return f"{topic} is an important concept from the uploaded material."
    if topic.lower() in text.lower():
        return text
    return f"{topic}: {text}"


def _unique_topic_rows(sections: list[dict[str, Any]], limit: int = 16) -> list[list[str]]:
    rows: list[list[str]] = []
    seen: set[str] = set()
    for section in sections:
        topic = _topic_title(section.get("title"), "Topic")
        key = topic.lower()
        if not topic or key in seen:
            continue
        seen.add(key)
        content = section.get("content") or section.get("educational_explanation") or section.get("explanation") or ""
        keywords = _dedupe(section.get("concept_keywords") or section.get("topics") or [], 3)
        definitions = _dedupe(section.get("definitions") or [], 2)
        examples = _dedupe(section.get("examples") or section.get("use_cases") or [], 1)
        mistakes = _dedupe(section.get("common_mistakes") or [], 1)
        meaning = definitions[0] if definitions else _shorten(content, sentences=1, chars=180)
        remember_parts = []
        if keywords:
            remember_parts.append(", ".join(keyword.title() for keyword in keywords))
        if examples:
            remember_parts.append(f"Example: {examples[0]}")
        if mistakes:
            remember_parts.append(f"Avoid: {mistakes[0]}")
        remember = " | ".join(remember_parts) or _shorten(content, sentences=1, chars=120)
        rows.append([topic, meaning, remember])
        if len(rows) >= limit:
            break
    return rows


def _useful_mindmap_label(value: Any) -> bool:
    label = _topic_title(value, "").lower()
    if len(label) < 3:
        return False
    generic = {
        "object",
        "instance",
        "used",
        "use",
        "page",
        "jsp",
        "java",
        "request",
        "response",
        "elements",
        "method",
        "methods",
        "name",
        "source",
        "file",
    }
    return label not in generic


def _mindmap_label(value: Any, fallback: str = "Concept") -> str:
    text = re.sub(r"[\[\]{}()<>|`\"']", " ", str(value or fallback))
    text = re.sub(r"\s+", " ", text).strip()
    return _topic_title((text or fallback)[:64], fallback)


def _aggregate_cornell(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    cues, notes, summaries = [], [], []
    for section in sections:
        cornell = section.get("notes", {}).get("cornell", {})
        section_title = _topic_title(section.get("title"), "Section")
        section_text = section.get("content") or section.get("educational_explanation") or cornell.get("notes", "")
        cues.extend(cornell.get("cue") or [])
        cues.extend(_cue_questions(section_title, section_text))
        cues.extend(section.get("test_yourself") or [])
        section_lines = []
        short_note = _meaning_sentence(section_title, section_text)
        if short_note:
            section_lines.append(f"- {short_note}")
        for label, values in [
            ("Definition", section.get("definitions") or []),
            ("Key point", section.get("key_points") or []),
            ("Example/use", (section.get("examples") or []) + (section.get("use_cases") or [])),
            ("Avoid", section.get("common_mistakes") or []),
            ("Revise", section.get("revision_notes") or []),
        ]:
            for value in _dedupe(values, 4 if label == "Key point" else 2):
                section_lines.append(f"- {label}: {value}")
        why = section.get("why_this_matters")
        if why:
            section_lines.append(f"- Why it matters: {_shorten(why, sentences=1, chars=220)}")
        if section_lines:
            notes.append(f"{section_title}\n" + "\n".join(section_lines))
        if cornell.get("summary"):
            summaries.append(_shorten(cornell["summary"], sentences=1, chars=180))
        elif section_text:
            summaries.append(_shorten(section_text, sentences=1, chars=180))
    return {
        "title": f"{title} - Cornell Notes",
        "format": "cornell",
        "cue": _dedupe(cues, 18),
        "notes": "\n\n".join(_dedupe([item for item in notes if item], 16)),
        "summary": _shorten(" ".join(summaries), sentences=3, chars=520),
    }


def _aggregate_outline(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    outline_sections = []
    for section in sections:
        points: list[str] = []
        for label, values in [
            ("Definition", section.get("definitions") or []),
            ("Core point", section.get("key_points") or []),
            ("Example/use", (section.get("examples") or []) + (section.get("use_cases") or [])),
            ("Important", section.get("important_notes") or []),
            ("Revision", section.get("revision_notes") or []),
        ]:
            for value in _dedupe(values, 5 if label == "Core point" else 2):
                points.append(f"{label}: {value}")
        if section.get("why_this_matters"):
            points.append(f"Why this matters: {_shorten(section.get('why_this_matters'), sentences=1, chars=220)}")
        if not points:
            points = [section.get("content") or section.get("educational_explanation") or section.get("explanation", "")]
        outline_sections.append(
            {
                "heading": section.get("title", "Section"),
                "points": points[:12],
            }
        )
    return {"title": f"{title} - Outline", "format": "outline", "sections": outline_sections}


def _aggregate_mindmap(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    branches = []
    lines = ["mindmap", f"  root(({_mindmap_label(title, 'Study Document')}))"]
    seen = set()
    for section in sections:
        section_name = _mindmap_label(section.get("title"), "Section")
        section_key = section_name.lower()
        if section_key in seen:
            continue
        seen.add(section_key)
        child_values = (
            section.get("topics")
            or section.get("concept_keywords")
            or section.get("notes", {}).get("mindmap", {}).get("branches", [])
            or []
        )
        children = []
        for child in child_values:
            child_name = child.get("name") if isinstance(child, dict) else child
            child_label = _mindmap_label(child_name, "")
            if child_label and _useful_mindmap_label(child_label):
                children.append({"name": child_label, "sub_branches": []})
            if len(children) >= 3:
                break
        child_names = _dedupe([child["name"] for child in children], 3)
        section_branch = {
            "name": section_name,
            "sub_branches": [{"name": child_name, "sub_branches": []} for child_name in child_names],
        }
        branches.append(section_branch)
        lines.append(f"    {_mindmap_label(section_branch['name'])}")
        for child in child_names:
            lines.append(f"      {_mindmap_label(child)}")
        if len(branches) >= 8:
            break
    return {
        "title": f"{title} - Mind Map",
        "format": "mindmap",
        "root": title,
        "mermaid": "\n".join(lines),
        "branches": branches,
    }


def _aggregate_chart(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    return {
        "title": f"{title} - Concept Chart",
        "format": "chart",
        "columns": ["Topic", "Simple Meaning", "Remember"],
        "rows": _unique_topic_rows(sections),
    }


def _aggregate_sentence(sections: list[dict[str, Any]], title: str, summary: str) -> str:
    paragraphs = [_shorten(summary, sentences=2, chars=420)]
    for section in sections:
        content = section.get("content") or section.get("educational_explanation") or section.get("notes", {}).get("sentence", "")
        sentence = _meaning_sentence(section.get("title"), content)
        if sentence:
            paragraphs.append(sentence)
        if len(paragraphs) >= 12:
            break
    return "\n\n".join(_dedupe([item for item in paragraphs if item], 12))


def _attach_section_questions(sections: list[dict[str, Any]], questions: list[dict[str, Any]]) -> None:
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for question in questions:
        by_topic.setdefault(str(question.get("topic") or "").lower(), []).append(question)
    for section in sections:
        section["questions"] = by_topic.get(str(section.get("title") or "").lower(), [])[:6]


def _build_package(
    text: str,
    filename: str,
    *,
    preferences: dict[str, Any] | None = None,
    extracted_diagrams: list[dict[str, Any]] | None = None,
    title_override: str | None = None,
    source_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned = _clean_text(text)
    title = title_override or _title_from_filename(filename)
    source_page_count = len(_split_pages(cleaned))
    difficulty = _difficulty_from_text(cleaned)
    target_note_pages = _target_note_pages(source_page_count)
    pref = {
        "note_depth": (preferences or {}).get(
            "note_depth",
            "focused_deep",
        ),
        "preferred_format": (preferences or {}).get("preferred_format", "cornell"),
        "exam_focus": bool((preferences or {}).get("exam_focus", True)),
        "include_examples": bool((preferences or {}).get("include_examples", True)),
        "include_diagrams": bool((preferences or {}).get("include_diagrams", True)),
        "document_title": title,
        "difficulty_level": difficulty,
        "source_page_count": source_page_count,
        "target_note_pages": target_note_pages,
        "educational_depth_policy": (
            "Use structural compression, not shallow summarization. "
            "Preserve definitions, core reasoning, procedures, formulas, "
            "examples, comparisons, important exceptions, diagrams, "
            "and source-specific terminology. Remove repetition, filler, "
            "generic introductions, and redundant explanations. "
            "The goal is high learning value per word."
        ),
        "generation_policy": {
            "batch_related_topics": True,
            "preferred_topics_per_api_call": "5-7 when source size permits",
            "avoid_one_call_per_topic": True,
            "target_output_ratio": (
                f"{target_note_pages['min']}-{target_note_pages['max']} "
                "note pages relative to the source document"
            ),
        },
        "structure_policy": (
            "Discover topics and subtopics from the uploaded document. "
            "Do not assume a fixed academic hierarchy and do not invent "
            "subject-specific sections that are not supported by the source."
        ),
    }
    pipeline = run_multi_pass_pipeline(
        cleaned,
        filename,
        diagrams=extracted_diagrams or [],
        preferences=pref,
        quiz_limit=max(12, min(40, (source_page_count or 1) * 2)),
    )
    intelligence = pipeline.get("document_intelligence") or {}
    sections = pipeline.get("sections") or []
    questions = pipeline.get("questions") or []
    _attach_section_questions(sections, questions)
    summary = intelligence.get("document_summary") or f"{title} converted into teacher-style study notes."
    package = {
        "document_title": title,
        "source_filename": filename,
        "source_files": source_files,
        "total_uploaded_files": len(source_files or [filename]),
        "total_sections": len(sections),
        "sections": sections,
        "notes": {
            "cornell": _aggregate_cornell(sections, title),
            "outline": _aggregate_outline(sections, title),
            "mindmap": _aggregate_mindmap(sections, title),
            "chart": _aggregate_chart(sections, title),
            "sentence": _aggregate_sentence(sections, title, summary),
        },
        "diagrams": [diagram for section in sections for diagram in section.get("diagrams", [])],
        "questions": questions,
        "global_summary": summary,
        "document_intelligence": intelligence,
        "topic_map": intelligence,
        "difficulty_level": difficulty,
        "note_volume_policy": {
            "source_pages": source_page_count,
            "target_note_pages": target_note_pages,
            "rule": "Premium notes should preserve 50-70% educational depth instead of overcompressing the source.",
        },
        "pipeline_diagnostics": {
            "pipeline": [
                "extract_complete_text",
                "full_document_understanding",
                "document_intelligence_map",
                "semantic_educational_structuring",
                "human_like_note_generation",
                "revision_optimization",
                "advanced_quiz_generation",
            ],
            "chunking_position": "after_full_document_llm_understanding",
            "chunking_strategy": "document-intelligence-topic-sections",
            "structure_policy": "domain-agnostic; discover topics from source content",
            "content_policy": "source-grounded; preserve educationally important detail",
            "section_count": len(sections),
            "source_quality": intelligence.get("source_quality", {}),
            "analysis_mode": intelligence.get("analysis_mode", "fallback"),
        },
        "preferences": pref,
        "generation_mode": "llm" if intelligence.get("analysis_mode") == "llm" else "fallback",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return package


def generate_note_package(
    text: str,
    filename: str,
    preferences: dict[str, Any] | None = None,
    extracted_diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _build_package(
        text,
        filename,
        preferences=preferences,
        extracted_diagrams=extracted_diagrams,
    )


def _session_title(documents: list[dict[str, Any]]) -> str:
    titles = [_title_from_filename(str(doc.get("filename") or "Document")) for doc in documents]
    titles = _dedupe(titles, 3)
    if not titles:
        return "Combined Study Session"
    if len(titles) == 1:
        return titles[0]
    suffix = "" if len(documents) <= 3 else f" + {len(documents) - 3} more"
    return f"Study Session: {', '.join(titles)}{suffix}"


def generate_session_note_package(
    documents: list[dict[str, Any]],
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid_documents = [
        {
            "filename": str(doc.get("filename") or f"document-{index + 1}.txt"),
            "text": _clean_text(str(doc.get("text") or "")),
            "size_kb": doc.get("size_kb", 0),
            "diagrams": doc.get("diagrams") or [],
        }
        for index, doc in enumerate(documents)
        if str(doc.get("text") or "").strip()
    ]
    if not valid_documents:
        valid_documents = [{"filename": "Study Session", "text": "No extracted text found.", "size_kb": 0, "diagrams": []}]

    title = _session_title(valid_documents)
    combined_text_parts = []
    diagrams = []
    source_files = []
    for index, doc in enumerate(valid_documents, start=1):
        combined_text_parts.append(f"Source file: {doc['filename']}\n{doc['text']}")
        source_files.append(
            {
                "filename": doc["filename"],
                "size_kb": doc.get("size_kb", 0),
                "page_count": len(_split_pages(doc["text"])),
                "diagram_count": len(doc.get("diagrams") or []),
            }
        )
        for diagram in doc.get("diagrams") or []:
            diagrams.append({**diagram, "source_filename": doc["filename"], "source_index": index})
    return _build_package(
        "\n\n".join(combined_text_parts),
        "multi-document-session",
        preferences=preferences,
        extracted_diagrams=diagrams,
        title_override=title,
        source_files=source_files,
    )


def format_package_for_view(package: dict[str, Any], note_format: str) -> dict[str, Any]:
    note_format = note_format.lower()
    notes = package.get("notes", {})
    sections = package.get("sections") or []
    title = package.get("document_title") or package.get("title") or "Study Document"
    if note_format == "full":
        return package
    if sections:
        if note_format == "cornell":
            return _aggregate_cornell(sections, title)
        if note_format == "outline":
            return _aggregate_outline(sections, title)
        if note_format == "mindmap":
            return _aggregate_mindmap(sections, title)
        if note_format == "chart":
            return _aggregate_chart(sections, title)
        if note_format == "sentence":
            return _aggregate_sentence(sections, title, package.get("global_summary") or "")
    if note_format in notes:
        return notes[note_format]
    return notes.get("cornell", {})


def generate_targeted_note_package(
    context: str,
    topic: str,
    source_metadata: dict[str, Any],
    preferences: dict[str, Any] | None = None,
    extracted_diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from services.targeted_note_generation import generate_targeted_note_package as _gen
    return _gen(
        context,
        topic,
        source_metadata,
        preferences=preferences,
        extracted_diagrams=extracted_diagrams,
    )