from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

MIN_MEANINGFUL_TITLE_WORDS = 1
MIN_CONTENT_WORDS = 8

QUALITY_THRESHOLDS = {
    "excellent": 0.90,
    "good": 0.75,
    "acceptable": 0.60,
}


# ============================================================
# GENERIC ARTIFACT PATTERNS
# ============================================================

PROMPT_LEAKAGE_PATTERNS = (
    r"\bread these ideas as a connected explanation\b",
    r"\bbefore moving (?:further|on)\b",
    r"\bconnect .+ with .+ when writing answers\b",
    r"\bwhen writing answers\b",
    r"\buse exact source terminology\b",
    r"\bwrite only the definition\b",
    r"\blisting .+ as isolated terms\b",
    r"\bskipping examples or use cases\b",
    r"\bwhen the question asks for application\b",
    r"\bfollow (?:these|the) instructions?\b",
    r"\buse (?:these|the) instructions?\b",
    r"\bsystem prompt\b",
    r"\buser prompt\b",
    r"\bas an ai\b",
    r"\bas a language model\b",
)


# ============================================================
# BASIC HELPERS
# ============================================================

def _clean(value: Any) -> str:
    return " ".join(
        str(value or "").strip().split()
    )


def _word_count(value: Any) -> int:
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


def _contains_prompt_leakage(value: Any) -> bool:
    text = _clean(value)

    if not text:
        return False

    lowered = text.lower()

    return any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in PROMPT_LEAKAGE_PATTERNS
    )


def _similar(
    left: str,
    right: str,
    threshold: float = 0.94,
) -> bool:
    a = _clean(left).lower()
    b = _clean(right).lower()

    if not a or not b:
        return False

    if a == b:
        return True

    if min(len(a), len(b)) < 30:
        return False

    return (
        SequenceMatcher(
            None,
            a,
            b,
        ).ratio()
        >= threshold
    )


def _has_meaningful_text(value: Any) -> bool:
    text = _clean(value)

    if not text:
        return False

    return (
        len(
            re.findall(
                r"\b[\w+#.-]+\b",
                text,
            )
        )
        >= MIN_CONTENT_WORDS
    )


# ============================================================
# SECTION VALIDATION
# ============================================================

def validate_section(
    section: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """
    Validate one normalized educational section.

    This function does not modify the section.
    It only reports quality problems.
    """

    issues: list[str] = []
    warnings: list[str] = []

    title = _clean(
        section.get("title")
    )

    content = _clean(
        section.get("content")
        or section.get("educational_explanation")
        or section.get("explanation")
    )

    definitions = section.get(
        "definitions"
    ) or []

    examples = section.get(
        "examples"
    ) or []

    key_points = section.get(
        "key_points"
    ) or []

    source_pages = section.get(
        "source_pages"
    ) or section.get(
        "page_numbers"
    ) or []

    diagrams = section.get(
        "diagrams"
    ) or []

    note_structure = section.get("note_structure") or {}
    structure_type = (
        note_structure.get("structure_type")
        if isinstance(note_structure, dict)
        else ""
    )
    structure_blocks = (
        note_structure.get("blocks") or []
        if isinstance(note_structure, dict)
        else []
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    if not title:
        issues.append(
            "missing_title"
        )

    elif len(
        re.findall(
            r"\b[\w+#.-]+\b",
            title,
        )
    ) < MIN_MEANINGFUL_TITLE_WORDS:
        issues.append(
            "meaningless_title"
        )

    # --------------------------------------------------------
    # CONTENT
    # --------------------------------------------------------

    if not content:
        issues.append(
            "missing_content"
        )

    elif not _has_meaningful_text(
        content
    ):
        warnings.append(
            "very_short_content"
        )

    # --------------------------------------------------------
    # PROMPT LEAKAGE
    # --------------------------------------------------------

    combined_text = " ".join(
        [
            content,
            title,
            " ".join(
                str(item)
                for item in definitions
            ),
            " ".join(
                str(item)
                for item in examples
            ),
            " ".join(
                str(item)
                for item in key_points
            ),
        ]
    )

    if _contains_prompt_leakage(
        combined_text
    ):
        issues.append(
            "prompt_leakage"
        )

    # --------------------------------------------------------
    # DUPLICATE CONTENT
    # --------------------------------------------------------

    text_candidates = []

    if content:
        text_candidates.append(
            content
        )

    text_candidates.extend(
        _clean(item)
        for item in key_points
        if _clean(item)
    )

    text_candidates.extend(
        _clean(item)
        for item in definitions
        if _clean(item)
    )

    duplicates = []

    for i in range(
        len(text_candidates)
    ):
        for j in range(
            i + 1,
            len(text_candidates),
        ):
            if _similar(
                text_candidates[i],
                text_candidates[j],
            ):
                duplicates.append(
                    {
                        "first": i,
                        "second": j,
                    }
                )

    if duplicates:
        warnings.append(
            "duplicate_content"
        )

    # --------------------------------------------------------
    # ADAPTIVE NOTE STRUCTURE
    # --------------------------------------------------------

    if not isinstance(note_structure, dict):
        issues.append("invalid_note_structure")
    else:
        if not _clean(structure_type):
            issues.append("missing_structure_type")

        if not isinstance(structure_blocks, list) or not structure_blocks:
            warnings.append("no_note_structure_blocks")
        elif len(structure_blocks) > 6:
            warnings.append("too_many_note_structure_blocks")

        for block_index, block in enumerate(structure_blocks):
            if not isinstance(block, dict):
                issues.append(
                    f"invalid_note_structure_block_{block_index}"
                )
                continue

            if not _clean(block.get("heading")):
                warnings.append(
                    f"note_structure_block_{block_index}_missing_heading"
                )

            if not _clean(block.get("block_type")):
                warnings.append(
                    f"note_structure_block_{block_index}_missing_type"
                )

    # --------------------------------------------------------
    # SOURCE PAGE METADATA
    # --------------------------------------------------------

    if not source_pages:
        warnings.append(
            "missing_source_pages"
        )

    elif not all(
        isinstance(
            page,
            (int, float),
        )
        and int(page) > 0
        for page in source_pages
    ):
        issues.append(
            "invalid_source_pages"
        )

    # --------------------------------------------------------
    # DIAGRAM VALIDATION
    # --------------------------------------------------------

    if diagrams:
        for diagram_index, diagram in enumerate(
            diagrams
        ):

            if not isinstance(
                diagram,
                dict,
            ):
                issues.append(
                    f"invalid_diagram_{diagram_index}"
                )
                continue

            diagram_id = diagram.get(
                "id"
            )

            if not diagram_id:
                warnings.append(
                    f"diagram_{diagram_index}_missing_id"
                )

            diagram_page = diagram.get(
                "page_number"
            )

            if (
                diagram_page is not None
                and (
                    not isinstance(
                        diagram_page,
                        (int, float),
                    )
                    or int(diagram_page) <= 0
                )
            ):
                issues.append(
                    f"diagram_{diagram_index}_invalid_page"
                )

    # --------------------------------------------------------
    # SECTION SCORE
    # --------------------------------------------------------

    score = 1.0

    # Major problems.
    score -= 0.25 * len(
        issues
    )

    # Minor problems.
    score -= 0.07 * len(
        warnings
    )

    score = max(
        0.0,
        min(
            1.0,
            score,
        ),
    )

    if score >= QUALITY_THRESHOLDS[
        "excellent"
    ]:
        rating = "excellent"

    elif score >= QUALITY_THRESHOLDS[
        "good"
    ]:
        rating = "good"

    elif score >= QUALITY_THRESHOLDS[
        "acceptable"
    ]:
        rating = "acceptable"

    else:
        rating = "poor"

    return {
        "section_index": index,
        "section_id": section.get(
            "section_id"
        )
        or section.get("id"),
        "title": title,
        "word_count": _word_count(
            section
        ),
        "score": round(
            score,
            3,
        ),
        "rating": rating,
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "checks": {
            "title_exists": bool(
                title
            ),
            "content_exists": bool(
                content
            ),
            "content_meaningful": _has_meaningful_text(
                content
            ),
            "prompt_leakage": _contains_prompt_leakage(
                combined_text
            ),
            "key_points_present": bool(
                key_points
            ),
            "definitions_present": bool(
                definitions
            ),
            "examples_present": bool(
                examples
            ),
            "note_structure_present": bool(
                isinstance(note_structure, dict)
                and bool(structure_type)
                and bool(structure_blocks)
            ),
            "note_structure_type": structure_type,
            "source_pages_present": bool(
                source_pages
            ),
            "diagrams_valid": not any(
                item.startswith(
                    "invalid_diagram"
                )
                or item.endswith(
                    "_invalid_page"
                )
                for item in issues
            ),
        },
    }


# ============================================================
# DOCUMENT-LEVEL DUPLICATE HEADING CHECK
# ============================================================

def _find_duplicate_titles(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    duplicates = []
    seen: list[
        tuple[int, str]
    ] = []

    for index, section in enumerate(
        sections
    ):

        title = _clean(
            section.get("title")
        )

        if not title:
            continue

        for previous_index, previous_title in seen:

            if _similar(
                title,
                previous_title,
                threshold=0.92,
            ):
                duplicates.append(
                    {
                        "first_index": previous_index,
                        "second_index": index,
                        "title": title,
                    }
                )

        seen.append(
            (
                index,
                title,
            )
        )

    return duplicates


# ============================================================
# DOCUMENT-LEVEL SOURCE COVERAGE
# ============================================================

def _source_page_coverage(
    sections: list[dict[str, Any]],
    expected_pages: int | None,
) -> dict[str, Any]:

    pages: set[int] = set()

    for section in sections:

        source_pages = (
            section.get(
                "source_pages"
            )
            or section.get(
                "page_numbers"
            )
            or []
        )

        if isinstance(
            source_pages,
            int,
        ):
            source_pages = [
                source_pages
            ]

        for page in source_pages:

            if isinstance(
                page,
                (int, float),
            ) and int(page) > 0:

                pages.add(
                    int(page)
                )

    if not expected_pages:
        return {
            "known": False,
            "pages_referenced": sorted(
                pages
            ),
            "coverage": None,
        }

    expected = set(
        range(
            1,
            expected_pages + 1,
        )
    )

    coverage = (
        len(
            pages & expected
        )
        / len(expected)
        if expected
        else 1.0
    )

    return {
        "known": True,
        "pages_referenced": sorted(
            pages
        ),
        "coverage": round(
            coverage,
            3,
        ),
        "missing_pages": sorted(
            expected - pages
        ),
    }


# ============================================================
# DOCUMENT VALIDATION
# ============================================================

def validate_note_package(
    package: dict[str, Any],
    *,
    expected_source_pages: int | None = None,
) -> dict[str, Any]:
    """
    Validate the normalized StudyAI note package.

    Expected input:

        {
            "note": {...},
            "sections": [...],
            "section_content": [...],
            "formats": [...],
            "diagrams": [...],
            "quiz": {...}
        }

    Returns a report without modifying the package.
    """

    package = (
        package
        if isinstance(
            package,
            dict,
        )
        else {}
    )

    note = package.get(
        "note"
    ) or {}

    sections = package.get(
        "sections"
    ) or []

    section_content = package.get(
        "section_content"
    ) or []

    diagrams = package.get(
        "diagrams"
    ) or []

    # --------------------------------------------------------
    # BASIC PACKAGE CHECKS
    # --------------------------------------------------------

    document_issues: list[str] = []
    document_warnings: list[str] = []

    if not isinstance(
        note,
        dict,
    ):
        document_issues.append(
            "invalid_note_metadata"
        )
        note = {}

    if not sections:
        document_issues.append(
            "no_sections"
        )

    if not section_content:
        document_issues.append(
            "no_section_content"
        )

    # --------------------------------------------------------
    # MERGE SECTION METADATA + CONTENT FOR VALIDATION
    # --------------------------------------------------------

    content_by_id = {}

    for content in section_content:

        if not isinstance(
            content,
            dict,
        ):
            continue

        section_id = content.get(
            "section_id"
        )

        if section_id:
            content_by_id[
                section_id
            ] = content

    validation_sections = []

    for section in sections:

        if not isinstance(
            section,
            dict,
        ):
            continue

        section_id = section.get(
            "id"
        )

        content = content_by_id.get(
            section_id,
            {},
        )

        merged = {
            **content,
            **section,
        }

        validation_sections.append(
            merged
        )

    # If sections aren't linked by IDs,
    # fall back to section_content.
    if not validation_sections:
        validation_sections = [
            item
            for item in section_content
            if isinstance(
                item,
                dict,
            )
        ]

    # --------------------------------------------------------
    # VALIDATE EACH SECTION
    # --------------------------------------------------------

    section_reports = []

    for index, section in enumerate(
        validation_sections
    ):

        report = validate_section(
            section,
            index,
        )

        section_reports.append(
            report
        )

    # --------------------------------------------------------
    # DUPLICATE TITLES
    # --------------------------------------------------------

    duplicate_titles = (
        _find_duplicate_titles(
            validation_sections
        )
    )

    if duplicate_titles:
        document_warnings.append(
            "duplicate_section_titles"
        )

    # --------------------------------------------------------
    # DIAGRAM VALIDATION
    # --------------------------------------------------------

    valid_diagrams = 0
    invalid_diagrams = 0

    for diagram in diagrams:

        if not isinstance(
            diagram,
            dict,
        ):
            invalid_diagrams += 1
            continue

        if not diagram.get("id"):
            invalid_diagrams += 1
            continue

        valid_diagrams += 1

    if invalid_diagrams:
        document_warnings.append(
            "invalid_diagram_metadata"
        )

    # --------------------------------------------------------
    # SOURCE COVERAGE
    # --------------------------------------------------------

    source_coverage = (
        _source_page_coverage(
            validation_sections,
            expected_source_pages,
        )
    )

    if (
        source_coverage["known"]
        and source_coverage["coverage"] < 0.80
    ):
        document_warnings.append(
            "low_source_page_coverage"
        )

    # --------------------------------------------------------
    # AGGREGATE SECTION METRICS
    # --------------------------------------------------------

    total_sections = len(
        section_reports
    )

    valid_sections = sum(
        1
        for report in section_reports
        if report["valid"]
    )

    prompt_leakage_sections = sum(
        1
        for report in section_reports
        if report["checks"][
            "prompt_leakage"
        ]
    )

    empty_content_sections = sum(
        1
        for report in section_reports
        if not report["checks"][
            "content_exists"
        ]
    )

    duplicate_content_sections = sum(
        1
        for report in section_reports
        if "duplicate_content"
        in report["warnings"]
    )

    if total_sections:
        section_validity = (
            valid_sections
            / total_sections
        )
    else:
        section_validity = 0.0

    average_section_score = (
        sum(
            report["score"]
            for report in section_reports
        )
        / total_sections
        if total_sections
        else 0.0
    )

    # --------------------------------------------------------
    # DOCUMENT QUALITY SCORE
    # --------------------------------------------------------

    score = average_section_score

    # Penalize document-level issues.
    score -= (
        0.08
        * len(document_issues)
    )

    score -= (
        0.03
        * len(document_warnings)
    )

    if total_sections:
        score -= (
            0.10
            * (
                prompt_leakage_sections
                / total_sections
            )
        )

        score -= (
            0.05
            * (
                empty_content_sections
                / total_sections
            )
        )

    score = max(
        0.0,
        min(
            1.0,
            score,
        ),
    )

    # --------------------------------------------------------
    # FINAL RATING
    # --------------------------------------------------------

    if score >= QUALITY_THRESHOLDS[
        "excellent"
    ]:
        rating = "excellent"

    elif score >= QUALITY_THRESHOLDS[
        "good"
    ]:
        rating = "good"

    elif score >= QUALITY_THRESHOLDS[
        "acceptable"
    ]:
        rating = "acceptable"

    else:
        rating = "poor"

    # --------------------------------------------------------
    # PASS / FAIL
    # --------------------------------------------------------

    # A document passes when:
    # - there are sections,
    # - most sections are structurally valid,
    # - no major prompt leakage exists,
    # - and the overall score is acceptable.

    passed = (
        bool(section_reports)
        and section_validity >= 0.80
        and prompt_leakage_sections == 0
        and score >= QUALITY_THRESHOLDS[
            "acceptable"
        ]
        and not document_issues
    )

    # --------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------

    return {
        "valid": passed,
        "quality_score": round(
            score,
            3,
        ),
        "rating": rating,
        "summary": {
            "total_sections": total_sections,
            "valid_sections": valid_sections,
            "invalid_sections": (
                total_sections
                - valid_sections
            ),
            "section_validity": round(
                section_validity,
                3,
            ),
            "average_section_score": round(
                average_section_score,
                3,
            ),
            "prompt_leakage_sections": (
                prompt_leakage_sections
            ),
            "empty_content_sections": (
                empty_content_sections
            ),
            "duplicate_content_sections": (
                duplicate_content_sections
            ),
            "duplicate_section_titles": len(
                duplicate_titles
            ),
            "valid_diagrams": valid_diagrams,
            "invalid_diagrams": invalid_diagrams,
        },
        "document_issues": document_issues,
        "document_warnings": document_warnings,
        "duplicate_titles": duplicate_titles,
        "source_coverage": source_coverage,
        "sections": section_reports,
    }


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def quality_check(
    package: dict[str, Any],
    *,
    expected_source_pages: int | None = None,
) -> dict[str, Any]:
    """
    Short public alias for application code.
    """
    return validate_note_package(
        package,
        expected_source_pages=expected_source_pages,
    )