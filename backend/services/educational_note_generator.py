from __future__ import annotations

import json
import re
from typing import Any

from ai_generation import generate_structured_json, has_llm_support
from semantic_utils import top_keywords


# ============================================================
# LLM RESPONSE SCHEMA
# ============================================================

NARRATIVE_NOTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "definitions": {"type": "array", "items": {"type": "string"}},
        "examples": {"type": "array", "items": {"type": "string"}},
        "use_cases": {"type": "array", "items": {"type": "string"}},
        "important_notes": {"type": "array", "items": {"type": "string"}},
        "why_this_matters": {"type": "string"},
        "common_mistakes": {"type": "array", "items": {"type": "string"}},
        "revision_notes": {"type": "array", "items": {"type": "string"}},
        "memory_tricks": {"type": "array", "items": {"type": "string"}},
        "concept_comparisons": {"type": "array", "items": {"type": "string"}},
        "test_yourself": {"type": "array", "items": {"type": "string"}},
        "note_structure": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "structure_type": {"type": "string"},
                "blocks": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "heading": {"type": "string"},
                            "block_type": {"type": "string"},
                            "content": {"type": "string"},
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 8,
                            },
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 8,
                            },
                            "rows": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 8,
                                },
                                "maxItems": 8,
                            },
                        },
                        "required": [
                            "heading",
                            "block_type",
                            "content",
                            "items",
                            "columns",
                            "rows",
                        ],
                    },
                },
            },
            "required": ["structure_type", "blocks"],
        },
    },
    "required": [
        "title",
        "content",
        "key_points",
        "note_structure",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def _clean_label(
    value: Any,
    fallback: str = "Concept",
) -> str:

    text = re.sub(
        r"[\[\]{}()<>|`\"']",
        " ",
        str(value or fallback),
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return (text or fallback)[:64]


def _clean_text(value: Any) -> str:

    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("â€¢", "-").replace("â— ", "-").replace("â—¦", "-")
    text = text.replace("●", "-").replace("•", "-").replace("○", "-")
    text = re.sub(r"\[SOURCE\s+\d+[^\]]*\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ).strip()


def _sentences(value: Any) -> list[str]:

    text = _clean_text(value)
    text = re.sub(r"\s+", " ", text)

    return [
        item.strip(" -\t")
        for item in re.split(r"(?<=[.!?])\s+", text)
        if item.strip(" -\t")
    ]


def _compact(value: Any, *, limit: int = 260) -> str:

    text = " ".join(str(value or "").split())

    if len(text) <= limit:
        return text

    trimmed = text[:limit].rsplit(" ", 1)[0].strip()

    return f"{trimmed}..." if trimmed else text[:limit]


def _dedupe_items(
    values: list[Any] | None,
    *,
    limit: int = 6,
    chars: int = 260,
) -> list[str]:

    seen = set()
    output = []

    for value in values or []:

        text = _compact(value, limit=chars)
        key = text.lower()

        if (
            not text
            or key in seen
            or re.fullmatch(r"\d+\.?", text)
            or len(re.findall(r"[A-Za-z][A-Za-z0-9+-]*", text)) < 3
        ):
            continue

        seen.add(key)
        output.append(text)

        if len(output) >= limit:
            break

    return output


def _source_points(raw: str, *, limit: int = 7) -> list[str]:

    candidates: list[str] = []

    for line in _clean_text(raw).splitlines():

        cleaned = line.strip(" -:\t")

        if (
            cleaned
            and len(cleaned) <= 320
            and len(re.findall(r"[A-Za-z][A-Za-z0-9+-]*", cleaned)) >= 4
        ):
            candidates.append(cleaned)

    candidates.extend(_sentences(raw))

    return _dedupe_items(
        candidates,
        limit=limit,
        chars=300,
    )


def _definition_candidates(raw: str, content: str) -> list[str]:

    patterns = [
        r"\b([A-Z][A-Za-z0-9 +#()/-]{2,70})\s+(?:is|are|refers to|means|is defined as)\s+([^.!?\n]{20,220})",
        r"\b([A-Z][A-Za-z0-9 +#()/-]{2,70})\s*:\s+([^.!?\n]{20,220})",
    ]

    candidates = []
    source = raw or content

    for pattern in patterns:

        for match in re.finditer(pattern, source):

            term = " ".join(match.group(1).split())
            meaning = " ".join(match.group(2).split())

            if term and meaning and "read these ideas" not in meaning.lower():
                candidates.append(f"{term}: {meaning}")

    return _dedupe_items(
        candidates,
        limit=5,
        chars=300,
    )


def _matching_sentences(
    source: str,
    pattern: str,
    *,
    limit: int = 4,
) -> list[str]:

    return _dedupe_items(
        [
            sentence
            for sentence in _sentences(source)
            if re.search(pattern, sentence, re.I)
        ],
        limit=limit,
        chars=300,
    )



def _infer_structure_type(
    title: str,
    raw: str,
    *,
    diagram_context: list[dict[str, Any]] | None = None,
) -> str:
    """Infer a generic learning structure from the source, not the subject."""
    text = f"{title}\n{raw}".lower()

    if diagram_context and any(
        diagram.get("caption") or diagram.get("context_text")
        for diagram in diagram_context
    ):
        return "diagram_or_architecture"

    if re.search(
        r"\b(vs\.?|versus|compared with|comparison|difference between|whereas|"
        r"distinguish between|differentiate)\b",
        text,
    ):
        return "comparison"

    if re.search(
        r"\b(formula|equation|calculate|calculation|mathematical|"
        r"probability|theorem|proof|derivation)\b"
        or r"(?<!\w)[A-Za-z]\s*=\s*[^=]",
        text,
    ):
        return "formula_or_derivation"

    if re.search(
        r"\b(step\s*\d+|steps|procedure|process|workflow|pipeline|"
        r"first.*then|then.*finally|followed by|consists of)\b",
        text,
        re.S,
    ):
        return "process_or_procedure"

    if re.search(
        r"\b(types of|type of|classified into|classification|categories|"
        r"categorized into|kinds of|variants)\b",
        text,
    ):
        return "classification"

    if re.search(
        r"\b(is defined as|are defined as|refers to|means|is a|is an)\b",
        text,
    ):
        return "definition_and_concept"

    if re.search(
        r"\b(advantages|disadvantages|benefits|limitations|applications|"
        r"use cases|examples|characteristics|properties)\b",
        text,
    ):
        return "concept_with_supporting_details"

    return "conceptual_explanation"


def _build_fallback_structure(
    title: str,
    raw: str,
    content: str,
    *,
    diagram_context: list[dict[str, Any]] | None = None,
    generated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a grounded structural outline when the LLM structure is absent."""
    generated_structure = (generated or {}).get("note_structure")
    if isinstance(generated_structure, dict):
        structure_type = _compact(
            generated_structure.get("structure_type")
            or _infer_structure_type(title, raw, diagram_context=diagram_context),
            limit=60,
        )
        blocks = generated_structure.get("blocks")
        if isinstance(blocks, list):
            cleaned_blocks = []
            for block in blocks[:6]:
                if not isinstance(block, dict):
                    continue
                heading = _compact(block.get("heading"), limit=100)
                block_type = _compact(block.get("block_type"), limit=50) or "text"
                if not heading:
                    continue
                cleaned_blocks.append({
                    "heading": heading,
                    "block_type": block_type,
                    "content": _compact(block.get("content"), limit=900),
                    "items": _dedupe_items(block.get("items") or [], limit=8, chars=280),
                    "columns": _dedupe_items(block.get("columns") or [], limit=8, chars=80),
                    "rows": [
                        _dedupe_items(row, limit=8, chars=180)
                        for row in (block.get("rows") or [])[:8]
                        if isinstance(row, list)
                    ],
                })
            if cleaned_blocks:
                return {
                    "structure_type": structure_type,
                    "blocks": cleaned_blocks,
                }

    structure_type = _infer_structure_type(
        title,
        raw or content,
        diagram_context=diagram_context,
    )
    source_points = _source_points(raw or content, limit=6)
    definitions = _definition_candidates(raw, content)[:3]
    examples = _matching_sentences(
        raw or content,
        r"\b(example|for example|such as|instance)\b",
        limit=3,
    )
    process_steps = _matching_sentences(
        raw or content,
        r"\b(step\s*\d+|first|second|third|then|next|finally|procedure|process)\b",
        limit=6,
    )
    comparison_lines = _matching_sentences(
        raw or content,
        r"\b(vs\.?|versus|whereas|difference|differentiate|compared)\b",
        limit=5,
    )
    formula_lines = _matching_sentences(
        raw or content,
        r"(?<!\w)[A-Za-z]\s*=\s*[^=]+|formula|equation|theorem|proof|derivation",
        limit=4,
    )

    blocks = []
    if structure_type == "definition_and_concept" and definitions:
        blocks.append({
            "heading": "Definition",
            "block_type": "definition",
            "content": "",
            "items": definitions,
            "columns": [],
            "rows": [],
        })

    if structure_type == "process_or_procedure" and process_steps:
        blocks.append({
            "heading": "Process / Steps",
            "block_type": "steps",
            "content": "",
            "items": process_steps,
            "columns": [],
            "rows": [],
        })

    if structure_type == "comparison" and comparison_lines:
        blocks.append({
            "heading": "Comparison",
            "block_type": "comparison",
            "content": "",
            "items": comparison_lines,
            "columns": [],
            "rows": [],
        })

    if structure_type == "formula_or_derivation" and formula_lines:
        blocks.append({
            "heading": "Formula / Derivation",
            "block_type": "formula",
            "content": "",
            "items": formula_lines,
            "columns": [],
            "rows": [],
        })

    if examples:
        blocks.append({
            "heading": "Example",
            "block_type": "example",
            "content": "",
            "items": examples,
            "columns": [],
            "rows": [],
        })

    remaining = [p for p in source_points if p not in definitions and p not in examples]
    if remaining:
        blocks.append({
            "heading": "Core Ideas",
            "block_type": "key_points",
            "content": "",
            "items": remaining[:6],
            "columns": [],
            "rows": [],
        })

    if not blocks:
        blocks.append({
            "heading": title,
            "block_type": "explanation",
            "content": _compact(content or raw, limit=1200),
            "items": [],
            "columns": [],
            "rows": [],
        })

    return {
        "structure_type": structure_type,
        "blocks": blocks[:6],
    }


def _fallback_study_aids(
    section: dict[str, Any],
    title: str,
    content: str,
) -> dict[str, Any]:
    """Build only source-supported aids; never invent pedagogical facts."""
    raw = str(section.get("raw_text") or content or "").strip()

    key_points = _source_points(raw, limit=7)
    definitions = _definition_candidates(raw, content)
    examples = _matching_sentences(
        raw,
        r"\b(example|for example|such as|like|instance)\b",
        limit=4,
    )
    use_cases = _matching_sentences(
        raw,
        r"\b(use|used|application|practical|helps|supports|enables|allows|handles)\b",
        limit=4,
    )
    important_notes = _matching_sentences(
        raw,
        r"\b(important|note|however|but|except|limitation|advantage|disadvantage|"
        r"must|should|cannot|only|always|never)\b",
        limit=5,
    )
    why_sentence = _matching_sentences(
        raw,
        r"\b(important|significant|benefit|advantage|useful|helps|enables|"
        r"allows|purpose|goal|objective)\b",
        limit=1,
    )
    common_mistakes = _matching_sentences(
        raw,
        r"\b(mistake|error|incorrect|wrong|avoid|pitfall|confus|misunderstand)\b",
        limit=4,
    )
    revision_notes = _dedupe_items(
        definitions[:2] + key_points[:4],
        limit=5,
        chars=260,
    )
    comparisons = _matching_sentences(
        raw,
        r"\b(vs\.?|versus|whereas|compared|difference|differentiate|distinguish)\b",
        limit=4,
    )

    # Questions may be generated from the section title, but their answers
    # remain grounded in the supplied content.
    test_yourself = _dedupe_items(
        [
            f"What is {title}?",
            f"How does {title} work or function according to the material?",
            f"What are the key points of {title}?",
            *[
                f"Explain this example or application: {item}"
                for item in examples[:2]
            ],
        ],
        limit=5,
        chars=220,
    )

    return {
        "key_points": key_points,
        "definitions": definitions,
        "examples": examples,
        "use_cases": use_cases,
        "important_notes": important_notes,
        "why_this_matters": _compact(
            why_sentence[0] if why_sentence else "",
            limit=300,
        ),
        "common_mistakes": common_mistakes,
        "revision_notes": revision_notes,
        "memory_tricks": [],
        "concept_comparisons": comparisons,
        "test_yourself": test_yourself,
    }


def _merge_study_aids(
    generated: dict[str, Any] | None,
    section: dict[str, Any],
    title: str,
    content: str,
) -> dict[str, Any]:
    """
    Prefer the LLM's source-grounded answer.

    Fallback extraction is used only when a field is genuinely absent.
    An explicitly empty LLM field is respected, preventing generic
    filler from being reintroduced after generation.
    """
    fallback = _fallback_study_aids(section, title, content)
    generated = generated or {}
    merged: dict[str, Any] = {}

    array_keys = [
        "key_points",
        "definitions",
        "examples",
        "use_cases",
        "important_notes",
        "common_mistakes",
        "revision_notes",
        "memory_tricks",
        "concept_comparisons",
        "test_yourself",
    ]

    for key in array_keys:
        if key in generated and isinstance(generated.get(key), list):
            values = generated.get(key) or []
        else:
            values = fallback.get(key, [])

        merged[key] = _dedupe_items(
            values,
            limit=7 if key == "key_points" else 5,
            chars=320,
        )

    if "why_this_matters" in generated:
        why = generated.get("why_this_matters") or ""
    else:
        why = fallback.get("why_this_matters") or ""

    merged["why_this_matters"] = _compact(
        why,
        limit=360,
    )

    return merged


def _mindmap(
    title: str,
    keywords: list[str],
) -> dict[str, Any]:

    useful_keywords = [
        keyword
        for keyword in keywords
        if keyword.lower()
        not in {
            "object",
            "instance",
            "used",
            "page",
            "request",
            "response",
            "method",
        }
    ][:4]

    branches = [
        {
            "name": keyword.title(),
            "sub_branches": [],
        }
        for keyword in useful_keywords
    ]

    lines = [
        "mindmap",
        f"  root(({_clean_label(title)}))",
    ]

    for branch in branches:
        lines.append(
            f"    {_clean_label(branch['name'])}"
        )

    return {
        "root": title,
        "mermaid": "\n".join(lines),
        "branches": branches,
    }


def _humanize_source(
    raw: str,
    title: str,
    diagram_context: list[dict[str, Any]] | None = None,
) -> str:
    """Return readable source-grounded fallback text without invented teaching filler."""
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", raw or "")
        if item.strip()
    ]

    if not sentences:
        return (
            f"{title}: very little readable text was extracted from the "
            "uploaded material."
        )

    content = " ".join(sentences[:18])

    if diagram_context:
        captions = [
            diagram.get("caption") or diagram.get("context_text")
            for diagram in diagram_context
            if diagram.get("caption") or diagram.get("context_text")
        ]
        if captions:
            content += "\n\nRelated visual: " + "; ".join(captions[:3])

    return content.strip()


def _compat_note_payload(
    title: str,
    content: str,
    keywords: list[str],
    study_aids: dict[str, Any],
) -> dict[str, Any]:

    clean_keywords = [
        keyword.title()
        for keyword in keywords
        if keyword.lower()
        not in {
            "object",
            "instance",
            "used",
            "page",
            "request",
            "response",
            "method",
        }
    ][:3]

    first_sentence = re.split(
        r"(?<=[.!?])\s+",
        " ".join(content.split()),
    )[0][:220]

    key_points = study_aids.get("key_points") or []
    definitions = study_aids.get("definitions") or []
    examples = study_aids.get("examples") or []
    test_yourself = study_aids.get("test_yourself") or []
    revision_notes = study_aids.get("revision_notes") or []

    outline_points = (
        [f"Definition: {item}" for item in definitions[:2]]
        + key_points[:5]
        + [f"Example/use: {item}" for item in examples[:2]]
        + [f"Revision: {item}" for item in revision_notes[:2]]
    )

    cornell_notes = content

    if key_points:

        cornell_notes += (
            "\n\nExam-ready points:\n"
            + "\n".join(
                f"- {point}"
                for point in key_points[:5]
            )
        )

    if definitions:

        cornell_notes += (
            "\n\nDefinitions to know:\n"
            + "\n".join(
                f"- {definition}"
                for definition in definitions[:4]
            )
        )

    return {
        "cornell": {
            "cue": [
                f"What is {title}?",
                f"Why is {title} important?",
                *test_yourself[:4],
            ],
            "notes": cornell_notes.strip(),
            "summary": first_sentence,
        },

        "outline": {
            "title": title,
            "sections": [
                {
                    "heading": title,
                    "points": outline_points or [content],
                }
            ],
        },

        "mindmap": _mindmap(
            title,
            keywords,
        ),

        "chart": [
            [
                title,
                first_sentence,
                ", ".join(clean_keywords)
                or "Main idea",
            ]
        ],

        "sentence": content,
    }


# ============================================================
# FINAL SECTION PAYLOAD
# ============================================================

def _section_payload(
    section: dict[str, Any],
    title: str,
    content: str,
    diagram_context: list[dict[str, Any]] | None = None,
    generated: dict[str, Any] | None = None,
) -> dict[str, Any]:

    keywords = (
        section.get("concept_keywords")
        or top_keywords(
            f"{title} {content}",
            limit=10,
        )
    )

    study_aids = _merge_study_aids(
        generated,
        section,
        title,
        content,
    )

    note_structure = _build_fallback_structure(
        title,
        str(section.get("raw_text") or ""),
        content,
        diagram_context=diagram_context,
        generated=generated,
    )

    return {
        "title": title,

        "content": content,

        "educational_explanation": content,

        "explanation": content,

        "topics": (
            section.get("related_topics")
            or keywords[:6]
        ),

        "key_points": study_aids["key_points"],

        "definitions": study_aids["definitions"],

        "examples": study_aids["examples"],

        "use_cases": study_aids["use_cases"],

        "important_notes": study_aids["important_notes"],

        "why_this_matters": study_aids["why_this_matters"],

        "common_mistakes": study_aids["common_mistakes"],

        "revision_notes": study_aids["revision_notes"],

        "memory_tricks": study_aids["memory_tricks"],

        "concept_comparisons": study_aids["concept_comparisons"],

        "test_yourself": study_aids["test_yourself"],

        "note_structure": note_structure,

        "notes": _compat_note_payload(
            title,
            content,
            keywords,
            study_aids,
        ),

        "narrative_style": "natural-teaching",

        "inline_diagram_refs": [
            {
                "page_number": diagram.get(
                    "page_number"
                ),
                "caption": (
                    diagram.get("caption")
                    or diagram.get("context_text")
                ),
            }
            for diagram in (
                diagram_context or []
            )
        ],
    }


# ============================================================
# AI TEACHING NARRATIVE
# ============================================================

def generate_teaching_narrative(
    section: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    preferences: dict[str, Any] | None = None,
    diagram_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

    title = (
        section.get("title")
        or "Study Topic"
    )

    raw = section.get(
        "raw_text",
        "",
    )

    # --------------------------------------------------------
    # No LLM available
    # --------------------------------------------------------

    if not has_llm_support():

        print(
            f"[NOTE FALLBACK] "
            f"{title} | LLM unavailable"
        )

        content = _humanize_source(
            raw,
            title,
            diagram_context,
        )

        return _section_payload(
            section,
            title,
            content,
            diagram_context,
        )

    # --------------------------------------------------------
    # Estimate reasonable output size
    # --------------------------------------------------------

    source_words = max(
        len(re.findall(r"\w+", raw)),
        1,
    )

    # Don't blindly expand tiny sections into huge notes.
    target_words = min(
        650,
        max(
            180,
            round(source_words * 0.45),
        ),
    )

    # --------------------------------------------------------
    # SYSTEM PROMPT
    # --------------------------------------------------------

    system_prompt = """
You are the teaching-note generator for an AI study platform.

Your job is to transform the uploaded study material into
clear, useful, accurate notes that a student can actually study.

SOURCE-GROUNDING IS THE MOST IMPORTANT RULE.

Use the supplied source text as the primary authority.

Do not invent facts, definitions, examples, formulas, protocols,
steps, advantages, disadvantages, or applications that are not
supported by the source material.

You may improve grammar, ordering, clarity, and explanation,
but you must preserve the meaning of the uploaded material.

If the source is incomplete or ambiguous, do not confidently
invent the missing information.

The final explanation should feel like a good teacher explaining
the topic to a student.

Write natural connected prose rather than a collection of
artificial AI sections.

Do NOT create rigid headings such as:

- Key Points
- Workflow
- Exam Practice
- Definitions
- Applications
- Advantages
- Disadvantages
- Revision Strategy
- MCQs
- Summary

unless such a structure is genuinely necessary for understanding
the source.

The note must use an ADAPTIVE STRUCTURAL FORMAT.
Choose the structure that best matches the supplied material:
conceptual_explanation, definition_and_concept, process_or_procedure,
comparison, formula_or_derivation, classification, concept_with_supporting_details,
diagram_or_architecture, or mixed.

Do not force a structure that the source does not support.
A process should preserve ordered steps. A comparison should preserve
the actual dimensions of comparison. A formula section should preserve
the formula, variables, conditions, and derivation only when present.
A diagram/architecture section should explain the visual relationships
using only the supplied diagram context and source.

Do not mention that you are an AI.

Do not mention the prompt.

Do not mention these instructions.

Return ONLY JSON containing:
title
content
key_points
definitions
examples
use_cases
important_notes
why_this_matters
common_mistakes
revision_notes
memory_tricks
concept_comparisons
test_yourself
note_structure

For study-aid arrays, return an empty array when the source does not
support that aid. Never manufacture a comparison, memory trick,
application, mistake, or example just to fill a field.

For note_structure, return:
- structure_type: the best generic learning structure
- blocks: 2-6 meaningful blocks in the order a student should learn them
Each block must use block_type such as definition, explanation, steps,
comparison, formula, example, classification, diagram, key_points, or
summary. Use items for bullets/steps. Use columns and rows only for a
real comparison/table supported by the source. Do not create empty
decorative blocks.
""".strip()

    # --------------------------------------------------------
    # USER PROMPT
    # --------------------------------------------------------

    section_memory = {
        key: value
        for key, value in section.items()
        if key != "raw_text"
    }

    # --------------------------------------------------------
    # COMPACT DOCUMENT CONTEXT
    # --------------------------------------------------------
    # Send only the document-level information needed to
    # explain the current section. Repeating the complete
    # intelligence object for every section wastes tokens.
    compact_intelligence = {
        "document_title": intelligence.get("document_title"),
        "subject": intelligence.get("subject"),
        "learning_objectives": intelligence.get(
            "learning_objectives",
            [],
        ),
        "key_topics": intelligence.get(
            "key_topics",
            [],
        ),
        "relationships": intelligence.get(
            "relationships",
            [],
        ),
    }

    user_prompt = (
        "DOCUMENT CONTEXT:\n"
        f"{json.dumps(compact_intelligence, ensure_ascii=True)}\n\n"

        "SECTION INFORMATION:\n"
        f"{json.dumps(section_memory, ensure_ascii=True)}\n\n"

        "STUDENT PREFERENCES:\n"
        f"{json.dumps(preferences or {}, ensure_ascii=True)}\n\n"

        f"TARGET LENGTH: approximately {target_words} words.\n\n"

        "DIAGRAM CONTEXT:\n"
        f"{json.dumps(diagram_context or [], ensure_ascii=True)}\n\n"

        "SOURCE TEXT — THIS IS THE PRIMARY MATERIAL:\n"
        "--------------------------------------------------\n"
        f"{raw}\n"
        "--------------------------------------------------\n\n"

        "Write the final teaching explanation using the source "
        "material above. Preserve important terminology from the "
        "source. Explain relationships between ideas where the "
        "source supports them. If a diagram belongs to this "
        "section, refer to it naturally in the explanation.\n\n"
        "Choose the note_structure that best matches the actual "
        "material rather than using a fixed template.\n\n"
        "Also extract study aids from the same source material. "
        "key_points should be exam-ready bullets, definitions should "
        "include term and meaning, examples/use_cases should only use "
        "examples or applications supported by the section, "
        "common_mistakes/revision_notes/test_yourself should help a "
        "student revise this exact section. Leave an aid empty when "
        "the source does not support it. Do not invent educational "
        "facts or examples."
    )

    # --------------------------------------------------------
    # CALL LLM
    # --------------------------------------------------------

    try:

        print(
            f"[LLM NOTE START] {title}"
        )

        generated = generate_structured_json(
            system_prompt,
            user_prompt,
            "teaching_narrative",
            NARRATIVE_NOTE_SCHEMA,

            temperature=0.36,

            # IMPORTANT:
            # Don't use the in-memory cache while testing.
            # Otherwise repeated tests may appear to finish
            # in 0.02 seconds without making a Groq request.
            cache=False,
        )

        content = str(
            generated.get("content")
            or ""
        ).strip()

        generated_title = str(
            generated.get("title")
            or title
        ).strip()

        if not content:

            raise ValueError(
                "Groq returned an empty note."
            )

        print(
            f"[LLM NOTE DONE] "
            f"{generated_title} | "
            f"{len(content)} chars"
        )

        return _section_payload(
            section,
            generated_title,
            content,
            diagram_context,
            generated,
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # Do not silently hide LLM failures.
    # --------------------------------------------------------

    except Exception as exc:

        print(
            "\n[NOTE GENERATION ERROR]"
            f"\nSection: {title}"
            f"\nType: {type(exc).__name__}"
            f"\nMessage: {exc}"
        )

        content = _humanize_source(
            raw,
            title,
            diagram_context,
        )

        return _section_payload(
            section,
            title,
            content,
            diagram_context,
        )


# ============================================================
# PUBLIC API
# ============================================================

def generate_human_notes(
    section: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    preferences: dict[str, Any] | None = None,
    diagram_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

    return generate_teaching_narrative(
        section,
        intelligence,
        preferences=preferences,
        diagram_context=diagram_context,
    )


def generate_teacher_style_notes(
    section: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    preferences: dict[str, Any] | None = None,
    diagram_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

    return generate_teaching_narrative(
        section,
        intelligence,
        preferences=preferences,
        diagram_context=diagram_context,
    )