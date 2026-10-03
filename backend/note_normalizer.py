from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4


REQUIRED_FORMATS = ("cornell", "outline", "mindmap", "chart", "sentence")


# ============================================================
# GENERIC LLM ARTIFACT DETECTION
# ============================================================
# These patterns are intentionally subject-independent.
# They detect generation instructions leaking into final notes,
# not concepts belonging to any particular academic domain.

_PROMPT_LEAKAGE_PATTERNS = (
    r"\bread these ideas as a connected explanation\b",
    r"\bbefore moving (?:further|on)\b",
    r"\bconnect .+ with .+ when writing answers\b",
    r"\bwhen writing answers\b",
    r"\buse exact source terminology\b",
    r"\bwrite only the definition\b",
    r"\blisting .+ as isolated terms\b",
    r"\bskipping examples or use cases\b",
    r"\bwhen the question asks for application\b",
    r"\bhere is (?:the|a) (?:study|note|summary)\b",
    r"\bthe following (?:notes|section|content)\b",
    r"\b(?:follow|use|apply) (?:these|the) instructions?\b",
    r"\b(?:system|user) prompt\b",
)


_MODULE_HEADER_RE = re.compile(
    r"^\s*module\s*\d+\s*$",
    re.IGNORECASE,
)

_PAGE_MARKER_RE = re.compile(
    r"^\s*\[\[page_\d+\]\]\s*$",
    re.IGNORECASE,
)

_SOURCE_HEADER_RE = re.compile(
    r"\[SOURCE\s+\d+[^\]]*\]\s*",
    re.IGNORECASE,
)

_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


# ============================================================
# BASIC HELPERS
# ============================================================

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _contains_prompt_leakage(value: Any) -> bool:
    """
    Return True when text contains a recognizable generation artifact.

    This does not depend on any subject such as networking, DBMS,
    mathematics, physics, etc.
    """
    text = str(value or "").strip()
    if not text:
        return False

    lowered = text.lower()

    return any(
        re.search(pattern, lowered)
        for pattern in _PROMPT_LEAKAGE_PATTERNS
    )


def _remove_prompt_segments(value: Any) -> str:
    """
    Remove only the instruction-like portion of a line.

    Example:

        Valid educational content...
        Read these ideas as a connected explanation...

    becomes:

        Valid educational content...

    This is safer than deleting the entire line because valid
    educational content may appear before the leaked instruction.
    """
    text = str(value or "").strip()

    if not text:
        return ""

    for pattern in _PROMPT_LEAKAGE_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        prefix = text[: match.start()].rstrip(" :-–—")

        if prefix:
            return prefix

        return ""

    return text


def _similar(
    left: str,
    right: str,
    threshold: float = 0.96,
) -> bool:
    """
    Detect exact or very-near duplicate strings.

    Short strings are not treated as near duplicates because short
    academic terms such as TCP, IP, or ARP can legitimately repeat.
    """
    a = re.sub(r"\s+", " ", left.strip().lower())
    b = re.sub(r"\s+", " ", right.strip().lower())

    if not a or not b:
        return False

    if a == b:
        return True

    if min(len(a), len(b)) < 35:
        return False

    return SequenceMatcher(None, a, b).ratio() >= threshold


def _clean_text(
    value: Any,
    limit: int | None = None,
) -> str:
    """
    Generic deterministic cleanup for generated educational text.

    Important:
    - Does not rewrite concepts.
    - Does not summarize.
    - Does not call an LLM.
    - Preserves useful educational content.
    """
    if value is None:
        return ""

    text = str(value)

    # Normalize common encoding / whitespace problems.
    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\ufeff", "")
        .replace("\x00", "")
        .replace("â€¢", "•")
        .replace("â—", "•")
        .replace("â—¦", "◦")
    )

    cleaned_lines: list[str] = []

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        # Remove page-processing markers.
        if _PAGE_MARKER_RE.fullmatch(line):
            continue

        # Remove standalone Module 1 / Module 2 / etc.
        if _MODULE_HEADER_RE.fullmatch(line):
            continue

        # Remove accidental module prefix attached to valid content.
        line = re.sub(
            r"^module\s*\d+\s*[:.)-]?\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )

        # Remove stray source metadata headers
        line = _SOURCE_HEADER_RE.sub("", line).strip()

        if not line:
            continue

        # Remove only the leaked instruction portion.
        line = _remove_prompt_segments(line)

        if not line:
            continue

        line = _WHITESPACE_RE.sub(" ", line).strip()

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    text = _MULTI_NEWLINE_RE.sub(
        "\n\n",
        text,
    ).strip()

    # Remove repeated lines/sentences generated accidentally.
    text = _remove_duplicate_lines_and_sentences(text)

    if limit is not None:
        text = text[:limit].rstrip()

    return text


def _dedupe(
    values: list[Any] | None,
    limit: int | None = None,
) -> list[str]:
    """
    Clean a list and remove exact / near duplicate entries.
    """
    output: list[str] = []

    for value in values or []:

        item = _clean_text(value)

        if not item:
            continue

        if _contains_prompt_leakage(item):
            continue

        if any(
            _similar(item, existing)
            for existing in output
        ):
            continue

        output.append(item)

        if limit is not None and len(output) >= limit:
            break

    return output


def _lower_keys(value: Any) -> Any:
    """
    Normalize dictionary keys recursively while preserving structure.
    """
    if isinstance(value, dict):
        return {
            str(key).lower(): _lower_keys(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _lower_keys(item)
            for item in value
        ]

    if isinstance(value, str):
        return _clean_text(value)

    return value


def _word_count(value: Any) -> int:
    """
    Count words recursively across strings, dictionaries and lists.
    """
    if isinstance(value, str):
        return len(
            re.findall(
                r"\b[\w+#.-]+\b",
                value,
            )
        )

    if isinstance(value, dict):
        return sum(
            _word_count(item)
            for item in value.values()
        )

    if isinstance(value, list):
        return sum(
            _word_count(item)
            for item in value
        )

    return 0


# ============================================================
# DUPLICATE CLEANUP
# ============================================================

def _remove_duplicate_lines_and_sentences(
    text: str,
) -> str:
    """
    Remove repeated generation artifacts while retaining order
    and educational meaning.
    """
    if not text:
        return ""

    lines = text.splitlines()

    output: list[str] = []

    for line in lines:

        stripped = line.strip()

        if not stripped:
            if output and output[-1] != "":
                output.append("")
            continue

        # Consecutive duplicate / near-duplicate lines.
        if (
            output
            and output[-1]
            and _similar(
                stripped,
                output[-1],
            )
        ):
            continue

        output.append(stripped)

    text = "\n".join(output)

    # Process paragraphs independently.
    paragraphs = re.split(
        r"\n{2,}",
        text,
    )

    cleaned_paragraphs: list[str] = []

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        sentences = re.split(
            r"(?<=[.!?])\s+",
            paragraph,
        )

        seen: list[str] = []
        unique_sentences: list[str] = []

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            if any(
                _similar(sentence, previous)
                for previous in seen
            ):
                continue

            seen.append(sentence)
            unique_sentences.append(sentence)

        if unique_sentences:
            cleaned_paragraphs.append(
                " ".join(unique_sentences)
            )

    return "\n\n".join(
        cleaned_paragraphs
    ).strip()


# ============================================================
# TITLE CLEANUP
# ============================================================

def _clean_title(
    value: Any,
    fallback: str = "Untitled Topic",
) -> str:
    title = _clean_text(value)

    # Remove generic numbering from generated titles.
    title = re.sub(
        r"^\s*(?:section|topic)\s*\d+\s*[:.)-]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"^\s*\d+(?:\.\d+)*\s*[:.)-]\s*",
        "",
        title,
    )

    # Remove accidental filename extensions.
    title = re.sub(
        r"\.(?:pdf|docx?|pptx?|txt)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip(" :-") or fallback


def _is_meaningful_section_title(value: Any) -> bool:
    """
    Generic validation for normalized section titles.
    Keeps short academic labels/acronyms while rejecting obvious prose
    fragments and UI/prompt artifacts.
    """
    title = _clean_title(value, "")
    if not title:
        return False

    normalized = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()

    generic = {
        "section", "topic", "simple", "type", "types", "working",
        "example", "examples", "details", "notes", "data", "module",
        "advantages", "disadvantages", "concept", "concepts",
    }

    if normalized in generic:
        return False

    if len(title.split()) > 14:
        return False

    if re.search(r"[.!?]$", title):
        return False

    if normalized.startswith((
        "here ", "this ", "these ", "if ", "when ", "because ",
        "which ", "where ", "users ", "device ", "devices ",
    )):
        return False

    return True


# ============================================================
# DIAGRAM CLEANUP
# ============================================================

def _clean_diagram(
    diagram: Any,
    section_id: str,
) -> dict[str, Any] | None:
    """
    Preserve diagram metadata while cleaning generated text fields.
    """
    if not isinstance(diagram, dict):
        return None

    clean = dict(diagram)

    clean["section_id"] = section_id

    for key in (
        "caption",
        "context_text",
        "ocr_text",
        "content",
        "explanation",
    ):
        if key in clean:
            clean[key] = _clean_text(
                clean.get(key),
                4000,
            )

    # Keep important metadata untouched:
    # id, page_number, image_path, image_url,
    # diagram_type, mermaid_code, etc.
    return clean


# ============================================================
# EMPTY FORMAT STRUCTURES
# ============================================================

def _empty_format(
    format_type: str,
) -> Any:

    if format_type == "cornell":
        return {
            "cue": [],
            "notes": "",
            "summary": "",
        }

    if format_type == "outline":
        return {
            "sections": [],
        }

    if format_type == "mindmap":
        return {
            "root": "",
            "branches": [],
        }

    if format_type == "chart":
        return {
            "columns": [],
            "rows": [],
        }

    return ""


# ============================================================
# MAIN NORMALIZATION PIPELINE
# ============================================================

def normalize_generated_notes(
    package: dict,
    subject: str | None = None,
) -> dict:
    """
    Convert the generated LLM package into a stable application schema.

    Phase 7 responsibilities:
        1. Remove prompt leakage.
        2. Remove duplicate content.
        3. Normalize whitespace.
        4. Preserve educational content.
        5. Preserve definitions/examples/formulas in source fields.
        6. Preserve source page metadata.
        7. Preserve diagrams.
        8. Preserve quiz questions.
        9. Avoid any additional LLM call.

    This function is deliberately domain-independent.
    """

    package = _lower_keys(
        package or {}
    )

    note_id = str(
        package.get("id")
        or uuid4()
    )

    created_at = (
        package.get("generated_at")
        or _now()
    )

    title = _clean_title(
        package.get("document_title")
        or package.get("title"),
        "Untitled Note",
    )

    raw_sections = [
        section
        for section in package.get("sections", [])
        if (
            isinstance(section, dict)
            and section.get("title")
            and _is_meaningful_section_title(section.get("title"))
        )
    ]

    tags = (
        package.get("tags")
        or ([subject] if subject else [])
    )

    # --------------------------------------------------------
    # NOTE METADATA
    # --------------------------------------------------------

    note = {
        "id": note_id,
        "title": title,
        "subject": _clean_text(
            subject
            or package.get("subject")
            or "general"
        ),
        "difficulty": _clean_text(
            package.get("difficulty_level")
            or ""
        ),
        "tags": _dedupe(tags),
        "created_at": created_at,
        "updated_at": _now(),
        "total_sections": len(raw_sections),
        "estimated_read_time": 0,
        "progress": 0,
        "is_favorite": False,
        "last_opened": None,
    }

    sections: list[dict[str, Any]] = []
    section_content: list[dict[str, Any]] = []
    formats: list[dict[str, Any]] = []
    diagrams: list[dict[str, Any]] = []

    all_questions = {
        "mcq": [],
        "short": [],
        "long": [],
    }

    # --------------------------------------------------------
    # SECTION NORMALIZATION
    # --------------------------------------------------------

    for order_index, source_section in enumerate(
        raw_sections
    ):

        section_id = str(
            source_section.get("section_id")
            or uuid4()
        )

        title_value = _clean_title(
            source_section.get("title"),
            f"Section {order_index + 1}",
        )

        content = _clean_text(
            source_section.get("content")
            or source_section.get(
                "educational_explanation"
            )
            or source_section.get(
                "explanation",
                "",
            ),
            12000,
        )

        explanation = _clean_text(
            source_section.get(
                "explanation",
                "",
            ),
            6000,
        )

        source_formats = (
            source_section.get("notes")
            or source_section.get("formats")
            or {}
        )

        if not isinstance(
            source_formats,
            dict,
        ):
            source_formats = {}

        # ----------------------------------------------------
        # EDUCATIONAL FIELDS
        # ----------------------------------------------------

        clean_topics = _dedupe(
            source_section.get("topics")
        )

        clean_key_points = _dedupe(
            source_section.get("key_points")
        )

        clean_definitions = _dedupe(
            source_section.get("definitions")
        )

        clean_examples = _dedupe(
            source_section.get("examples")
        )

        clean_use_cases = _dedupe(
            source_section.get("use_cases")
        )

        clean_important_notes = _dedupe(
            source_section.get("important_notes")
        )

        clean_common_mistakes = _dedupe(
            source_section.get("common_mistakes")
        )

        clean_test_yourself = _dedupe(
            source_section.get("test_yourself")
        )

        clean_why = _clean_text(
            source_section.get(
                "why_this_matters",
                "",
            ),
            2500,
        )

        # ----------------------------------------------------
        # QUESTIONS
        # ----------------------------------------------------

        questions = [
            question
            for question in (
                source_section.get("questions")
                or []
            )
            if isinstance(question, dict)
        ]

        # ----------------------------------------------------
        # SOURCE PAGE METADATA
        # ----------------------------------------------------

        page_numbers = (
            source_section.get("page_numbers")
            or source_section.get("source_pages")
            or []
        )

        if isinstance(
            page_numbers,
            int,
        ):
            page_numbers = [
                page_numbers
            ]

        page_numbers = [
            int(page)
            for page in page_numbers
            if (
                isinstance(
                    page,
                    (int, float),
                )
                and int(page) > 0
            )
        ]

        # ----------------------------------------------------
        # WORD COUNT
        # ----------------------------------------------------

        section_text_source = {
            "title": title_value,
            "topics": clean_topics,
            "content": content,
            "explanation": explanation,
            "key_points": clean_key_points,
            "definitions": clean_definitions,
            "examples": clean_examples,
            "use_cases": clean_use_cases,
            "important_notes": clean_important_notes,
            "why_this_matters": clean_why,
            "common_mistakes": clean_common_mistakes,
            "test_yourself": clean_test_yourself,
        }

        word_count = _word_count(
            section_text_source
        )

        # ----------------------------------------------------
        # SECTION METADATA
        # ----------------------------------------------------

        sections.append(
            {
                "id": section_id,
                "note_id": note_id,
                "title": title_value,
                "order_index": order_index,
                "word_count": word_count,
                "source_pages": page_numbers,
            }
        )

        # ----------------------------------------------------
        # SECTION CONTENT
        # ----------------------------------------------------

        section_content.append(
            {
                "section_id": section_id,
                "title": title_value,
                "topics": clean_topics,
                "content": content,
                "explanation": explanation,
                "key_points": clean_key_points,
                "definitions": clean_definitions,
                "examples": clean_examples,
                "use_cases": clean_use_cases,
                "important_notes": clean_important_notes,
                "why_this_matters": clean_why,
                "common_mistakes": clean_common_mistakes,
                "test_yourself": clean_test_yourself,
                "questions": questions,
                "source_pages": page_numbers,
                "source_filename": (
                    source_section.get(
                        "source_filename"
                    )
                    or package.get(
                        "source_filename"
                    )
                ),
            }
        )

        # ----------------------------------------------------
        # NOTE FORMATS
        # ----------------------------------------------------

        for format_type in REQUIRED_FORMATS:

            format_content = source_formats.get(
                format_type,
                _empty_format(
                    format_type
                ),
            )

            if isinstance(
                format_content,
                str,
            ):
                format_content = _clean_text(
                    format_content,
                    10000,
                )

            elif isinstance(
                format_content,
                dict,
            ):
                format_content = _lower_keys(
                    format_content
                )

            elif isinstance(
                format_content,
                list,
            ):
                format_content = _lower_keys(
                    format_content
                )

            formats.append(
                {
                    "section_id": section_id,
                    "format_type": format_type,
                    "content": format_content,
                }
            )

        # ----------------------------------------------------
        # DIAGRAMS
        # ----------------------------------------------------

        for diagram in (
            source_section.get("diagrams")
            or []
        ):

            clean_diagram = _clean_diagram(
                diagram,
                section_id,
            )

            if clean_diagram:
                diagrams.append(
                    clean_diagram
                )

        # ----------------------------------------------------
        # QUIZ QUESTIONS
        # ----------------------------------------------------

        for question in questions:

            q_type = str(
                question.get(
                    "type",
                    "short",
                )
            ).lower()

            if q_type == "mcq":

                all_questions["mcq"].append(
                    question
                )

            elif q_type in {
                "long",
                "theory",
                "application",
            }:

                all_questions["long"].append(
                    question
                )

            else:

                all_questions["short"].append(
                    question
                )

    # ========================================================
    # FINAL NOTE METRICS
    # ========================================================

    total_words = sum(
        section["word_count"]
        for section in sections
    )

    note["estimated_read_time"] = (
        max(
            1,
            round(
                total_words / 180
            ),
        )
        if sections
        else 0
    )

    # ========================================================
    # FINAL NORMALIZED PACKAGE
    # ========================================================

    result = {
        "note": note,
        "sections": sections,
        "section_content": section_content,
        "formats": formats,
        "diagrams": diagrams,
        "quiz": {
            "note_id": note_id,
            **all_questions,
        },
    }

    # Preserve useful package-level metadata.
    if package.get("source_filename"):
        result["source_filename"] = (
            package["source_filename"]
        )

    if package.get("source_files"):
        result["source_files"] = (
            package["source_files"]
        )

    if package.get("document_intelligence"):
        result["document_intelligence"] = (
            package["document_intelligence"]
        )

    if package.get("topic_map"):
        result["topic_map"] = (
            package["topic_map"]
        )

    if package.get("global_summary"):
        result["global_summary"] = _clean_text(
            package["global_summary"],
            5000,
        )

    return result