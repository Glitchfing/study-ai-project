from __future__ import annotations

import os
import re
from typing import Any

from ai_generation import generate_structured_json, has_llm_support
from semantic_utils import extraction_quality_report, top_keywords


# ============================================================
# CONFIGURATION
# ============================================================

# Document intelligence is intentionally mostly deterministic.
# The goal is to discover the source's own structure quickly and
# avoid spending an LLM call merely rediscovering obvious headings.
#
# LLM refinement is used only when the source structure is weak.

MAX_MAJOR_TOPICS = int(os.environ.get("STUDYAI_MAX_MAJOR_TOPICS", "12"))
MAX_SUBTOPICS = int(os.environ.get("STUDYAI_MAX_SUBTOPICS", "36"))
MAX_RELATIONSHIPS = int(os.environ.get("STUDYAI_MAX_RELATIONSHIPS", "20"))
LLM_REFINEMENT_MAX_CHARS = int(
    os.environ.get("STUDYAI_INTELLIGENCE_REFINEMENT_CHARS", "10000")
)


# These are structural labels, not subject-specific knowledge.
# They should remain inside their parent topic.
GENERIC_HEADINGS = {
    "simple",
    "type",
    "types",
    "working",
    "advantages",
    "disadvantages",
    "advantage",
    "disadvantage",
    "example",
    "examples",
    "notes",
    "details",
    "introduction",
    "overview",
    "information",
    "concept",
    "concepts",
    "key components",
    "implementation",
    "key concepts",
    "common frameworks",
    "limitations",
    "applications",
    "significance",
    "summary",
    "conclusion",
    "procedure",
    "process",
    "steps",
}

SUBHEADING_PREFIXES = (
    "step ",
    "significance of ",
    "applications of ",
    "types of ",
    "key components",
    "implementation",
    "key concepts",
    "common frameworks",
    "advantages",
    "disadvantages",
    "limitations",
    "preprocess the text",
    "creating the vocabulary",
    "building a co-occurrence matrix",
    "performing dot product",
    "training the word vectors",
    "embedding matrix",
)


# ============================================================
# SCHEMA
# ============================================================

DOCUMENT_INTELLIGENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_title": {"type": "string"},
        "document_summary": {"type": "string"},
        "major_topics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "subtopics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "concept_relationships": {
            "type": "array",
            "items": {"type": "string"},
        },
        "workflow_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "architecture_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "exam_priority_topics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "definition_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "diagram_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "topic_dependencies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "quiz_candidate_topics": {
            "type": "array",
            "items": {"type": "string"},
        },
        "revision_priority_order": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "document_title",
        "document_summary",
        "major_topics",
        "subtopics",
        "concept_relationships",
        "workflow_sections",
        "architecture_sections",
        "exam_priority_topics",
        "definition_sections",
        "diagram_sections",
        "topic_dependencies",
        "quiz_candidate_topics",
        "revision_priority_order",
    ],
}


# ============================================================
# BASIC HELPERS
# ============================================================

def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip(" :-\t•●▪◦–—")


def _unique_strings(
    values: Any,
    limit: int | None = None,
) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        item = _clean(value)
        if not item:
            continue

        key = item.casefold()
        if key in seen:
            continue

        seen.add(key)
        result.append(item)

        if limit is not None and len(result) >= limit:
            break

    return result


def _title_from_filename(filename: str) -> str:
    value = (
        str(filename or "Study Document")
        .rsplit(".", 1)[0]
        .replace("_", " ")
        .replace("-", " ")
    )
    return re.sub(r"\s+", " ", value).strip().title() or "Study Document"


def _normalize_heading(value: str) -> str:
    value = _clean(value)
    value = re.sub(r"^[\(\[\{]+", "", value)
    value = re.sub(r"[\)\]\}]+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _normalize_topic_key(value: str) -> str:
    value = _normalize_heading(value).casefold()
    value = re.sub(r"\b(?:in|for|of|the|a|an)\b", " ", value)
    value = re.sub(r"[^a-z0-9+#]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#]{2,}", value.casefold()))


def _similar_topic(a: str, b: str) -> bool:
    ka = _normalize_topic_key(a)
    kb = _normalize_topic_key(b)

    if not ka or not kb:
        return False

    if ka == kb or ka in kb or kb in ka:
        return True

    ta, tb = _tokens(ka), _tokens(kb)
    if not ta or not tb:
        return False

    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return overlap >= 0.80


def _is_bullet_marker(value: str) -> bool:
    return value.strip() in {"•", "-", "●", "○", "▪", "◦", "*", "‣"}


def _is_numbered_subheading(value: str) -> bool:
    value = _normalize_heading(value)
    return bool(
        re.match(r"^(?:\d+(?:\.\d+)*|[A-Za-z])[\s.)]+", value)
    )


def _is_sentence_like(value: str) -> bool:
    value = _normalize_heading(value)
    if not value:
        return True

    if value.endswith(
        (".", ",", ";", "?", "!", "”", "’", ")]", "]}", "}>")
    ):
        return True

    value = value.rstrip(" \t\"'”’)]}")
    words = value.split()
    capitalized = sum(
        1 for word in words if word[:1].isupper()
    )
    if len(words) >= 6 and capitalized <= 2:
        return True

    first = words[0].casefold()

    sentence_starters = {
        "this", "these", "those", "here", "when", "where",
        "which", "because", "if", "while", "although",
        "the", "a", "an", "it", "they", "we", "you",
        "after", "before", "now", "for", "as",
    }
    return first in sentence_starters


def _is_subheading(value: str) -> bool:
    low = _normalize_heading(value).casefold()
    if not low:
        return True

    if low in GENERIC_HEADINGS:
        return True

    if _is_numbered_subheading(low):
        return True

    return any(low.startswith(prefix) for prefix in SUBHEADING_PREFIXES)


def _looks_like_heading(
    line: str,
    previous_line: str = "",
) -> bool:
    raw_line = str(line or "").strip()
    if raw_line.startswith("(") and raw_line.endswith(")"):
        return False

    value = _normalize_heading(raw_line)

    if not value or len(value) > 100:
        return False

    # A line immediately following a bullet marker is normally
    # bullet content/example text, not a section heading.
    if _is_bullet_marker(previous_line):
        return False

    if _is_sentence_like(value):
        return False

    if _is_subheading(value):
        return True

    # Explicit document structure is a strong signal.
    if re.match(
        r"^(chapter|unit|module|topic|lecture|lesson|part)\b",
        value,
        re.I,
    ):
        return True

    # Numbered/lettered headings are structural children, not majors.
    if _is_numbered_subheading(value):
        return True

    words = value.split()

    # Avoid long fragments being mistaken for headings.
    if len(words) > 10:
        return False

    # Most typed headings are title-like. For OCR/handwriting, a
    # single compact proper/mixed-case token such as "Word2Vec" is
    # also accepted.
    capitalized = sum(
        1 for word in words if word[:1].isupper()
    )
    title_like = capitalized >= max(1, len(words) - 2)

    if title_like:
        return True

    if (
        len(words) == 1
        and re.match(r"^[A-Z][A-Za-z0-9+#.-]{2,}$", value)
        and (
            any(ch.islower() for ch in value)
            or any(ch.isdigit() for ch in value)
        )
    ):
        return True

    # Short lowercase fragments are overwhelmingly normal prose/OCR
    # continuation rather than headings.
    return False


# ============================================================
# PAGE PARSING
# ============================================================

def _parse_pages(text: str) -> list[dict[str, Any]]:
    text = text or ""
    matches = list(
        re.finditer(r"\[\[PAGE_(\d+)\]\]", text)
    )

    if not matches:
        return [{"page_number": 1, "text": text.strip()}]

    pages: list[dict[str, Any]] = []

    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        pages.append(
            {
                "page_number": page_number,
                "text": text[start:end].strip(),
            }
        )

    return pages


# ============================================================
# HEADING EVENTS
# ============================================================

def _heading_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for page in _parse_pages(text):
        raw_lines = page["text"].splitlines()

        for line_index, raw_line in enumerate(raw_lines):
            line = raw_line.strip()
            if not line:
                continue

            previous_line = (
                raw_lines[line_index - 1].strip()
                if line_index > 0
                else ""
            )

            if not _looks_like_heading(
                line,
                previous_line,
            ):
                continue

            title = _normalize_heading(line)
            if not title:
                continue

            events.append(
                {
                    "page": page["page_number"],
                    "line_index": line_index,
                    "title": title,
                    "is_subtopic": _is_subheading(title)
                    or _is_numbered_subheading(title),
                    "is_explicit": bool(
                        re.match(
                            r"^(chapter|unit|module|topic|lecture|lesson|part)\b",
                            title,
                            re.I,
                        )
                    ),
                }
            )

    return events


def _consolidate_titles(
    titles: list[str],
) -> list[str]:
    result: list[str] = []

    for raw in titles:
        title = _normalize_heading(raw)
        if not title:
            continue

        # Structural labels never become major topics.
        if _is_subheading(title) or _is_numbered_subheading(title):
            continue

        duplicate_index = next(
            (
                index
                for index, existing in enumerate(result)
                if _similar_topic(existing, title)
            ),
            None,
        )

        if duplicate_index is not None:
            # Prefer the more informative title.
            if len(title) > len(result[duplicate_index]):
                result[duplicate_index] = title
            continue

        result.append(title)

    return result


# ============================================================
# DOCUMENT TITLE
# ============================================================

def _document_title(
    filename: str,
    events: list[dict[str, Any]],
) -> str:
    for event in events[:5]:
        if event.get("is_explicit"):
            title = _normalize_heading(event["title"])
            title = re.sub(
                r"^(chapter|unit|module|topic|lecture|lesson|part)"
                r"\s*(?:\d+[\s:.-]*)?",
                "",
                title,
                flags=re.I,
            ).strip(" :-")
            if title:
                return title

    return _title_from_filename(filename)


# ============================================================
# TOPIC STRUCTURE
# ============================================================

def _build_topics(
    text: str,
    filename: str,
) -> list[dict[str, Any]]:
    pages = _parse_pages(text)
    events = _heading_events(text)

    major_titles = _consolidate_titles(
        [
            event["title"]
            for event in events
            if not event["is_subtopic"]
            and not event["is_explicit"]
        ]
    )

    # If explicit chapter/unit/module headings are the only strong
    # structural headings, keep their meaningful child headings.
    if len(major_titles) < 2:
        major_titles = _consolidate_titles(
            [
                event["title"]
                for event in events
                if not event["is_subtopic"]
            ]
        )

    # For weak documents, use compact page groups instead of creating
    # dozens of pseudo-topics.
    if len(major_titles) < 2:
        page_groups: list[str] = []
        for page in pages:
            keywords = top_keywords(
                page["text"],
                limit=3,
            )
            if keywords:
                page_groups.append(
                    " / ".join(
                        item.title()
                        for item in keywords
                    )
                )
        major_titles = _consolidate_titles(page_groups)

    # Hard upper bound is deliberately much lower than the old 20.
    major_titles = major_titles[:MAX_MAJOR_TOPICS]

    topics: list[dict[str, Any]] = []

    # Map major title occurrences back to the source heading events.
    major_events: list[dict[str, Any]] = []
    used_events: set[int] = set()

    for title in major_titles:
        best_index = None

        for index, event in enumerate(events):
            if index in used_events:
                continue
            if _similar_topic(event["title"], title):
                best_index = index
                break

        if best_index is not None:
            used_events.add(best_index)
            major_events.append(
                {
                    **events[best_index],
                    "title": title,
                    "_event_index": best_index,
                }
            )

    # Keep source order.
    major_events.sort(
        key=lambda item: (
            item["page"],
            item["line_index"],
        )
    )

    # Build page spans between major headings.
    for index, event in enumerate(major_events):
        start_page = event["page"]
        end_page = (
            major_events[index + 1]["page"] - 1
            if index + 1 < len(major_events)
            else pages[-1]["page_number"]
        )

        # A topic may start and end on the same page.
        if end_page < start_page:
            end_page = start_page

        topic_pages = [
            page["page_number"]
            for page in pages
            if start_page <= page["page_number"] <= end_page
        ]

        source_parts = [
            page["text"]
            for page in pages
            if page["page_number"] in topic_pages
        ]
        source_text = "\n".join(source_parts)

        # Determine child headings from the source-event range for this
        # major topic. This is page-independent and therefore works when
        # several topics share a PDF page.
        start_event_index = int(
            event.get("_event_index", 0)
        )

        end_event_index = (
            int(
                major_events[index + 1].get(
                    "_event_index",
                    len(events),
                )
            )
            if index + 1 < len(major_events)
            else len(events)
        )

        topic_subtopics: list[str] = []

        for child_event in events[
            start_event_index + 1 : end_event_index
        ]:
            if child_event["is_subtopic"]:
                topic_subtopics.append(
                    child_event["title"]
                )

        topic_subtopics = _unique_strings(
            topic_subtopics,
            16,
        )

        concepts = _unique_strings(
            top_keywords(
                f"{event['title']} {source_text}",
                limit=10,
            ),
            10,
        )

        lowered = source_text.casefold()

        definitions = (
            [event["title"]]
            if re.search(
                r"\b(is|are|means|defined as|refers to)\b",
                lowered,
            )
            else []
        )

        examples = (
            ["Examples are present in the source material."]
            if re.search(
                r"\b(example|for example|such as|instance)\b",
                lowered,
            )
            else []
        )

        workflows = (
            [event["title"]]
            if re.search(
                r"\b(step|steps|process|procedure|workflow|"
                r"flow|cycle|lifecycle|method)\b",
                lowered,
            )
            else []
        )

        tables = (
            [event["title"]]
            if re.search(
                r"\b(table|comparison|versus|vs\.)\b",
                lowered,
            )
            else []
        )

        diagrams = (
            [event["title"]]
            if re.search(
                r"\b(diagram|figure|architecture|"
                r"block diagram|flowchart|matrix)\b",
                lowered,
            )
            else []
        )

        topics.append(
            {
                "title": event["title"],
                "pages": sorted(set(topic_pages)),
                "concepts": concepts,
                "subtopics": topic_subtopics,
                "definitions": definitions,
                "examples": examples,
                "diagrams": diagrams,
                "tables": tables,
                "workflows": workflows,
                "relationships": [],
                "exam_signals": [],
            }
        )

    # If the title list was valid but event matching failed, use a
    # conservative page-based fallback.
    if len(topics) < 2:
        topics = []
        for page in pages:
            page_text = page["text"].strip()
            if not page_text:
                continue

            keywords = top_keywords(
                page_text,
                limit=3,
            )

            if not keywords:
                continue

            title = " / ".join(
                item.title()
                for item in keywords
            )

            topics.append(
                {
                    "title": title,
                    "pages": [page["page_number"]],
                    "concepts": keywords,
                    "subtopics": [],
                    "definitions": [],
                    "examples": [],
                    "diagrams": [],
                    "tables": [],
                    "workflows": [],
                    "relationships": [],
                    "exam_signals": [],
                }
            )

            if len(topics) >= min(MAX_MAJOR_TOPICS, 8):
                break

    return topics[:MAX_MAJOR_TOPICS]


# ============================================================
# DETERMINISTIC DOCUMENT MAP
# ============================================================

def _deterministic_analysis(
    text: str,
    filename: str,
    diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = _heading_events(text)
    topics = _build_topics(text, filename)

    major_topics = [
        topic["title"]
        for topic in topics
    ]

    subtopics: list[str] = []

    for topic in topics:
        subtopics.extend(
            topic.get("subtopics") or []
        )

    # Add source headings that were deliberately classified as
    # subtopics. This captures things such as implementation steps,
    # examples, applications, and process stages without promoting
    # them to major sections.
    subtopics.extend(
        event["title"]
        for event in events
        if event["is_subtopic"]
    )

    subtopics.extend(
        top_keywords(
            text,
            limit=MAX_SUBTOPICS,
        )
    )

    subtopics = _unique_strings(
        subtopics,
        MAX_SUBTOPICS,
    )

    relationships = []
    for index in range(
        min(
            len(major_topics) - 1,
            MAX_RELATIONSHIPS,
        )
    ):
        left = major_topics[index]
        right = major_topics[index + 1]
        relationships.append(
            f"{left} is followed by {right} in the source structure."
        )

    workflow_sections = _unique_strings(
        [
            topic["title"]
            for topic in topics
            if topic.get("workflows")
        ],
        MAX_MAJOR_TOPICS,
    )

    architecture_sections = _unique_strings(
        [
            topic["title"]
            for topic in topics
            if topic.get("diagrams")
        ],
        MAX_MAJOR_TOPICS,
    )

    definition_sections = _unique_strings(
        [
            topic["title"]
            for topic in topics
            if topic.get("definitions")
        ],
        MAX_MAJOR_TOPICS,
    )

    diagram_sections = _unique_strings(
        [
            _clean(
                diagram.get("caption")
                or diagram.get("context_text")
            )
            for diagram in diagrams or []
        ],
        MAX_MAJOR_TOPICS,
    )

    title = _document_title(
        filename,
        events,
    )

    topic_hierarchy = [
        {
            "title": topic["title"],
            "pages": topic["pages"],
            "subtopics": topic.get("subtopics", []),
            "concepts": topic.get("concepts", []),
            "content_signals": {
                "definitions": bool(topic.get("definitions")),
                "examples": bool(topic.get("examples")),
                "workflows": bool(topic.get("workflows")),
                "tables": bool(topic.get("tables")),
                "diagrams": bool(topic.get("diagrams")),
            },
        }
        for topic in topics
    ]

    return {
        "document_title": title,
        "document_summary": (
            f"{title} contains {len(major_topics)} "
            "major learning topics discovered from the "
            "document's own structure."
        ),
        "major_topics": _unique_strings(
            major_topics,
            MAX_MAJOR_TOPICS,
        ),
        "subtopics": subtopics,
        "concept_relationships": _unique_strings(
            relationships,
            MAX_RELATIONSHIPS,
        ),
        "workflow_sections": workflow_sections,
        "architecture_sections": architecture_sections,
        "exam_priority_topics": _unique_strings(
            major_topics,
            MAX_MAJOR_TOPICS,
        ),
        "definition_sections": definition_sections,
        "diagram_sections": diagram_sections,
        "topic_dependencies": _unique_strings(
            [
                (
                    f"Study {major_topics[index]} "
                    f"before {major_topics[index + 1]}."
                )
                for index in range(
                    min(
                        len(major_topics) - 1,
                        MAX_RELATIONSHIPS,
                    )
                )
            ],
            MAX_RELATIONSHIPS,
        ),
        "quiz_candidate_topics": _unique_strings(
            major_topics,
            MAX_MAJOR_TOPICS,
        ),
        "revision_priority_order": _unique_strings(
            major_topics,
            MAX_MAJOR_TOPICS,
        ),
        "topics": topics,
        "topic_hierarchy": topic_hierarchy,
        "analysis_mode": "deterministic",
    }


# ============================================================
# OPTIONAL LLM REFINEMENT
# ============================================================

def _build_refinement_context(
    text: str,
    filename: str,
    deterministic: dict[str, Any],
) -> str:
    pages = []

    for page in _parse_pages(text)[:80]:
        pages.append(
            {
                "page": page["page_number"],
                "headings": [
                    event["title"]
                    for event in _heading_events(
                        f"[[PAGE_{page['page_number']}]]\n{page['text']}"
                    )
                ][:8],
                "keywords": top_keywords(
                    page["text"],
                    limit=6,
                ),
            }
        )

    context = {
        "filename": filename,
        "detected_major_topics": deterministic.get(
            "major_topics",
            [],
        ),
        "detected_subtopics": deterministic.get(
            "subtopics",
            [],
        ),
        "page_structure": pages,
    }

    return str(context)[:LLM_REFINEMENT_MAX_CHARS]


def _refine_with_llm(
    text: str,
    filename: str,
    deterministic: dict[str, Any],
) -> dict[str, Any]:
    if not has_llm_support():
        return deterministic

    prompt = f"""
You are refining the structural map of an educational document.

The document may belong to ANY subject.

Do not write study notes.

Use only the supplied structural evidence.

IMPORTANT:
- Major topics must be true learning topics, not steps, examples,
  applications, advantages, limitations, or generic labels.
- Merge closely related or duplicate headings.
- Keep implementation steps and sub-concepts under their parent topic.
- Prefer a compact hierarchy: normally 3-12 major topics.
- Preserve the source terminology.
- Do not invent subject-specific topics.
- Return JSON only.

SOURCE STRUCTURE:
{_build_refinement_context(text, filename, deterministic)}
""".strip()

    try:
        result = generate_structured_json(
            (
                "You are a domain-agnostic document structure "
                "refinement engine. Return valid JSON only."
            ),
            prompt,
            "document_intelligence_refinement",
            DOCUMENT_INTELLIGENCE_SCHEMA,
            temperature=0.10,
            max_output_tokens=2200,
        )

        if not isinstance(result, dict):
            return deterministic

        refined = dict(deterministic)

        for field in (
            "document_title",
            "document_summary",
            "major_topics",
            "subtopics",
            "concept_relationships",
            "workflow_sections",
            "architecture_sections",
            "exam_priority_topics",
            "definition_sections",
            "diagram_sections",
            "topic_dependencies",
            "quiz_candidate_topics",
            "revision_priority_order",
        ):
            value = result.get(field)

            if isinstance(value, list):
                limit = (
                    MAX_MAJOR_TOPICS
                    if field in {
                        "major_topics",
                        "exam_priority_topics",
                        "quiz_candidate_topics",
                        "revision_priority_order",
                    }
                    else MAX_SUBTOPICS
                )

                cleaned = _unique_strings(
                    value,
                    limit,
                )

                if cleaned:
                    refined[field] = cleaned

            elif isinstance(value, str) and value.strip():
                refined[field] = _clean(value)

        # Run the same generic consolidation after LLM refinement.
        refined_major = _consolidate_titles(
            refined.get("major_topics") or []
        )

        if 2 <= len(refined_major) <= MAX_MAJOR_TOPICS:
            refined["major_topics"] = refined_major
            refined["exam_priority_topics"] = refined_major
            refined["quiz_candidate_topics"] = refined_major
            refined["revision_priority_order"] = refined_major

        # Preserve deterministic page-aware hierarchy.
        refined["topics"] = deterministic.get("topics", [])
        refined["topic_hierarchy"] = deterministic.get(
            "topic_hierarchy",
            [],
        )
        refined["analysis_mode"] = "hybrid"

        return refined

    except Exception as exc:
        print(
            "[INTELLIGENCE REFINEMENT FALLBACK]"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        return deterministic


# ============================================================
# MAIN PUBLIC FUNCTION
# ============================================================

def analyze_full_document(
    text: str,
    filename: str,
    *,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Fast, domain-agnostic document intelligence.

    Pipeline:
        extraction
             ↓
        deterministic hierarchy
             ↓
        optional compact LLM refinement for weak structure
             ↓
        semantic section building
             ↓
        batched note generation
    """
    text = text or ""

    page_count = max(
        1,
        len(
            re.findall(
                r"\[\[PAGE_\d+\]\]",
                text,
            )
        ),
    )

    quality = extraction_quality_report(
        text,
        page_count=page_count,
    )

    print("\n" + "=" * 80)
    print("DOCUMENT INTELLIGENCE: COMPACT HIERARCHICAL MODE")
    print("=" * 80)
    print(f"Pages: {page_count}")
    print(f"Characters: {len(text)}")

    deterministic = _deterministic_analysis(
        text,
        filename,
        diagrams,
    )

    major_topics = deterministic.get(
        "major_topics",
        [],
    )

    print(
        "[INTELLIGENCE] "
        f"Major topics after consolidation: {len(major_topics)}"
    )

    # Only spend an LLM request when local structure is genuinely weak.
    heading_count = len(_heading_events(text))
    needs_refinement = (
        len(major_topics) < 2
        or heading_count < 3
    )

    if needs_refinement:
        print(
            "[INTELLIGENCE] Weak source structure → "
            "one compact LLM refinement."
        )
        result = _refine_with_llm(
            text,
            filename,
            deterministic,
        )
    else:
        print(
            "[INTELLIGENCE] Strong source structure → "
            "no intelligence LLM call."
        )
        result = deterministic

    result["source_quality"] = quality
    result["page_count"] = page_count
    result["preferences_used"] = preferences or {}

    # Never let refinement remove the detailed page-aware map.
    result["topics"] = deterministic.get("topics", [])
    result["topic_hierarchy"] = deterministic.get(
        "topic_hierarchy",
        [],
    )

    print("\n" + "=" * 80)
    print("DOCUMENT INTELLIGENCE COMPLETE")
    print(f"Mode: {result.get('analysis_mode')}")
    print(f"Major topics: {len(result.get('major_topics') or [])}")
    print(f"Subtopics: {len(result.get('subtopics') or [])}")
    print("=" * 80)

    return result


# ============================================================
# BACKWARD COMPATIBILITY
# ============================================================

def generate_document_map(
    text: str,
    filename: str,
    diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return analyze_full_document(
        text,
        filename,
        diagrams=diagrams,
    )


def identify_topic_relationships(
    intelligence: dict[str, Any],
) -> list[str]:
    return list(
        intelligence.get("concept_relationships") or []
    )


def identify_exam_focus(
    intelligence: dict[str, Any],
) -> list[str]:
    return list(
        intelligence.get("exam_priority_topics") or []
    )


def detect_concept_hierarchy(
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "major_topics": list(
            intelligence.get("major_topics") or []
        ),
        "subtopics": list(
            intelligence.get("subtopics") or []
        ),
        "dependencies": list(
            intelligence.get("topic_dependencies") or []
        ),
        "topic_hierarchy": list(
            intelligence.get("topic_hierarchy") or []
        ),
    }


def detect_workflows(
    intelligence: dict[str, Any],
) -> list[str]:
    return list(
        intelligence.get("workflow_sections") or []
    )


def detect_architecture_sections(
    intelligence: dict[str, Any],
) -> list[str]:
    return list(
        intelligence.get("architecture_sections") or []
    )