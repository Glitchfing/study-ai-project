from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ai_generation import generate_structured_json, has_llm_support, image_bytes_to_data_url

BASE_DIR = Path(__file__).resolve().parent

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "your",
    "their",
    "into",
    "have",
    "has",
    "had",
    "not",
    "can",
    "will",
    "may",
    "shall",
    "should",
    "would",
    "could",
    "there",
    "here",
    "about",
    "been",
    "each",
    "when",
    "what",
    "which",
    "where",
    "how",
    "why",
    "through",
    "using",
    "use",
    "used",
    "our",
    "its",
    "it",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "is",
    "as",
    "or",
}

HEADING_PREFIXES = (
    "chapter",
    "unit",
    "module",
    "topic",
    "lecture",
    "lesson",
    "section",
    "part",
)

CONCEPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "topics": {"type": "array", "items": {"type": "string"}},
        "definitions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "meaning": {"type": "string"},
                },
                "required": ["term", "meaning"],
            },
        },
        "relationships": {"type": "array", "items": {"type": "string"}},
        "exam_focus": {"type": "array", "items": {"type": "string"}},
        "diagram_insights": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "topics", "definitions", "relationships", "exam_focus", "diagram_insights"],
}

SECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "explanation": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "definitions": {"type": "array", "items": {"type": "string"}},
        "examples": {"type": "array", "items": {"type": "string"}},
        "use_cases": {"type": "array", "items": {"type": "string"}},
        "important_notes": {"type": "array", "items": {"type": "string"}},
        "why_this_matters": {"type": "string"},
        "common_mistakes": {"type": "array", "items": {"type": "string"}},
        "test_yourself": {"type": "array", "items": {"type": "string"}},
        "notes": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "cornell": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "cue": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["cue", "notes", "summary"],
                },
                "outline": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "heading": {"type": "string"},
                                    "points": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["heading", "points"],
                            },
                        },
                    },
                    "required": ["title", "sections"],
                },
                "mindmap": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "root": {"type": "string"},
                        "mermaid": {"type": "string"},
                        "branches": {
                            "type": "array",
                            "items": {
                                "$ref": "#/$defs/mindmapNode"
                            },
                        },
                    },
                    "required": ["root", "mermaid", "branches"],
                },
                "chart": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                },
                "sentence": {"type": "string"},
            },
            "required": ["cornell", "outline", "mindmap", "chart", "sentence"],
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "difficulty": {"type": "string"},
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "answer_index": {"type": "integer"},
                    "answer_hint": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": [
                    "type",
                    "difficulty",
                    "question",
                    "options",
                    "answer_index",
                    "answer_hint",
                    "explanation",
                ],
            },
        },
    },
    "required": [
        "title",
        "explanation",
        "key_points",
        "definitions",
        "examples",
        "use_cases",
        "important_notes",
        "why_this_matters",
        "common_mistakes",
        "test_yourself",
        "notes",
        "questions",
    ],
    "$defs": {
        "mindmapNode": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "sub_branches": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/mindmapNode"},
                },
            },
            "required": ["name", "sub_branches"],
        }
    },
}


def _title_from_filename(filename: str) -> str:
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()


def _clean_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("•", "").replace("●", "").replace("◦", "")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    lines = [line.strip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _split_pages(text: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"\[\[PAGE_(\d+)\]\]", text))
    if not matches:
        return [{"page_number": 1, "text": text}]

    pages = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_text = text[start:end].strip()
        if page_text:
            pages.append({"page_number": int(match.group(1)), "text": page_text})
    return pages or [{"page_number": 1, "text": text}]


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if paragraphs:
        return paragraphs
    return [line.strip() for line in text.split("\n") if line.strip()]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]+", text.lower())
    counts = Counter(word for word in words if len(word) > 2 and word not in STOPWORDS)
    return [word.replace("_", " ") for word, _ in counts.most_common(limit)]


def _looks_like_heading(paragraph: str) -> bool:
    stripped = paragraph.strip(":").strip()
    if not stripped or len(stripped) > 90:
        return False
    lowered = stripped.lower()
    if lowered.startswith(HEADING_PREFIXES):
        return True
    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z].+$", stripped):
        return True
    words = stripped.split()
    title_case_words = sum(1 for word in words if word[:1].isupper())
    return len(words) <= 9 and title_case_words >= max(1, len(words) - 2)


def _normalize_heading(text: str, fallback: str) -> str:
    cleaned = re.sub(r"^\d+(\.\d+)*\s*", "", text).strip(":- ").strip()
    return cleaned or fallback


def _chunk_pages(text: str, filename: str) -> list[dict[str, Any]]:
    pages = _split_pages(text)
    chunks: list[dict[str, Any]] = []
    current_title = _title_from_filename(filename)
    current_parts: list[str] = []
    current_pages: list[int] = []

    def flush_chunk() -> None:
        nonlocal current_parts, current_pages, current_title
        joined = "\n\n".join(part for part in current_parts if part.strip()).strip()
        if not joined:
            return
        chunks.append(
            {
                "section_id": f"section-{len(chunks) + 1}",
                "title": current_title or f"Section {len(chunks) + 1}",
                "raw_text": joined,
                "page_numbers": sorted(set(current_pages)) or [1],
            }
        )
        current_parts = []
        current_pages = []

    for page in pages:
        paragraphs = _split_paragraphs(page["text"])
        for paragraph in paragraphs:
            if _looks_like_heading(paragraph):
                if current_parts:
                    flush_chunk()
                current_title = _normalize_heading(paragraph, current_title)
                current_pages = [page["page_number"]]
                continue
            current_parts.append(paragraph)
            current_pages.append(page["page_number"])
            if len(" ".join(current_parts)) > 2200:
                flush_chunk()
        if len(" ".join(current_parts)) > 2400:
            flush_chunk()

    flush_chunk()

    if not chunks:
        cleaned = _clean_text(text)
        chunks.append(
            {
                "section_id": "section-1",
                "title": _title_from_filename(filename),
                "raw_text": cleaned or "No extracted text found.",
                "page_numbers": [1],
            }
        )

    merged: list[dict[str, Any]] = []
    for chunk in chunks:
        if merged and len(chunk["raw_text"]) < 350:
            merged[-1]["raw_text"] = f"{merged[-1]['raw_text']}\n\n{chunk['raw_text']}".strip()
            merged[-1]["page_numbers"] = sorted(set(merged[-1]["page_numbers"] + chunk["page_numbers"]))
            continue
        merged.append(chunk)
    return merged


def _difficulty_from_text(text: str) -> str:
    length = len(text)
    if length < 1500:
        return "beginner"
    if length < 6000:
        return "intermediate"
    return "advanced"


def _revision_strategy(section_count: int, difficulty: str) -> str:
    if section_count <= 1:
        return "Review the note once on the same day, then answer the conceptual and theory questions aloud."
    if difficulty == "advanced":
        return "Use a 1-3-7 day revision cycle, redraw the diagrams, and practice long-form theory answers for each section."
    if difficulty == "intermediate":
        return "Use a 1-3-7 day revision cycle and alternate between explanation recall, diagram review, and exam-style questions."
    return "Start with the section summaries, then test yourself with the cue questions and application prompts."


def _target_note_pages(source_page_count: int) -> dict[str, int]:
    if source_page_count <= 1:
        return {"min": 1, "max": 2}
    return {
        "min": max(1, round(source_page_count * 0.35)),
        "max": max(2, round(source_page_count * 0.55)),
    }


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    seen = set()
    result = []
    for item in items:
        value = " ".join(str(item).split())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if limit and len(result) >= limit:
            break
    return result


def _extract_definitions(text: str, keywords: list[str]) -> list[str]:
    definitions = []
    for sentence in _sentences(text):
        match = re.match(r"^([A-Za-z][A-Za-z0-9\s()/\-]{1,60})\s+(is|are|refers to|means)\s+(.+)", sentence, re.I)
        if match:
            term = match.group(1).strip()
            meaning = match.group(3).strip().rstrip(".")
            definitions.append(f"{term}: {meaning}.")
    if definitions:
        return _dedupe(definitions, limit=4)
    return [f"{keyword.title()}: a core idea that should be defined in your own words during revision." for keyword in keywords[:3]]


def _build_branch_tree(section_title: str, keywords: list[str]) -> list[dict[str, Any]]:
    head = keywords[:6] or [section_title.lower()]
    branches = []
    group_size = 2
    for index in range(0, len(head), group_size):
        branch_name = head[index].title()
        child_terms = head[index + 1:index + group_size + 1]
        branches.append(
            {
                "name": branch_name,
                "sub_branches": [{"name": term.title(), "sub_branches": []} for term in child_terms] or [],
            }
        )
    return branches or [{"name": section_title, "sub_branches": []}]


def _mindmap_mermaid(root: str, branches: list[dict[str, Any]]) -> str:
    lines = ["mindmap", f"  root(({root}))"]

    def add_branch(node: dict[str, Any], depth: int) -> None:
        lines.append(f"{'  ' * depth}{node['name']}")
        for child in node.get("sub_branches", []):
            add_branch(child, depth + 1)

    for branch in branches:
        add_branch(branch, 2)
    return "\n".join(lines)


def _build_exam_questions(title: str, keywords: list[str], definitions: list[str]) -> list[dict[str, Any]]:
    focus = (keywords[0] if keywords else title).title()
    compare = (keywords[1] if len(keywords) > 1 else "related concepts").title()
    definition_term = definitions[0].split(":", 1)[0] if definitions else focus
    return [
        {
            "type": "mcq",
            "difficulty": "medium",
            "question": f"Which option best identifies the main focus of {title}?",
            "options": [
                f"Understanding {focus} and its role",
                f"Only memorizing isolated syntax",
                "Ignoring system interactions",
                "Studying unrelated background trivia",
            ],
            "answer_index": 0,
            "answer_hint": f"Look for the option that captures the core role of {focus}.",
            "explanation": f"The section centers on {focus} as a core concept rather than isolated facts.",
        },
        {
            "type": "conceptual",
            "difficulty": "medium",
            "question": f"Why is {focus} important when studying {title}?",
            "options": [],
            "answer_index": 0,
            "answer_hint": f"Explain the role of {focus}, the problem it solves, and how it connects to {compare}.",
            "explanation": f"Strong answers should connect {focus} to purpose, flow, and exam relevance.",
        },
        {
            "type": "theory",
            "difficulty": "hard",
            "question": f"Explain {title} in an exam-style answer and include the role of {definition_term} and {compare}.",
            "options": [],
            "answer_index": 0,
            "answer_hint": "Structure the answer with definition, working, significance, and one example or comparison.",
            "explanation": "This question checks whether the learner can write a full descriptive answer, not just a definition.",
        },
        {
            "type": "application",
            "difficulty": "hard",
            "question": f"How would you apply the ideas from {title} in a practical scenario or system design discussion?",
            "options": [],
            "answer_index": 0,
            "answer_hint": f"Describe a use case where {focus} influences design decisions, implementation, or troubleshooting.",
            "explanation": "Application questions measure whether the concept can be used beyond rote memorization.",
        },
    ]


def _fallback_section(chunk: dict[str, Any], document_title: str) -> dict[str, Any]:
    keywords = _keywords(chunk["raw_text"], limit=8)
    section_title = chunk["title"]
    definitions = _extract_definitions(chunk["raw_text"], keywords)
    explanation = (
        f"{section_title} in {document_title} concentrates on {', '.join(term.title() for term in keywords[:4]) or 'the central topic'}. "
        f"This part should be studied as a connected idea rather than as isolated lines from the source material. "
        f"For exam preparation, focus on what the concept does, how it fits into the larger system, and where it is typically applied."
    )
    key_points = _dedupe(
        [
            f"{section_title} should be understood by purpose, flow, and relationship to surrounding concepts.",
            f"Important keywords in this section include {', '.join(term.title() for term in keywords[:4]) or section_title}.",
            "Learners should be ready to define the concept, describe its working, and explain one practical use.",
            "Revision should include comparison, application, and common exam phrasing.",
        ],
        limit=4,
    )
    examples = [
        f"Explain {section_title} using a short real-world or software-oriented example.",
        f"Relate {keywords[0].title() if keywords else section_title} to one implementation or workflow scenario.",
    ]
    use_cases = [
        f"Use {section_title} while discussing architecture, workflow, or implementation decisions.",
        "Use the concept to justify design choices or explain system behavior in a written answer.",
    ]
    important_notes = [
        "Do not memorize the section line by line; focus on meaning and relationships.",
        "In exams, strong answers usually include definition, working, use case, and one comparison.",
    ]
    common_mistakes = [
        f"Confusing {keywords[0].title() if keywords else section_title} with nearby related terms.",
        "Writing only a definition without explaining working or significance.",
        "Skipping the practical implication or architecture link in long answers.",
    ]
    test_yourself = [
        f"Can you explain {section_title} without looking at the source text?",
        f"Can you compare {keywords[0].title() if keywords else section_title} with another related concept?",
        "Can you draw or describe the process/architecture from memory if asked in an exam?",
    ]
    branches = _build_branch_tree(section_title, keywords)
    chart_rows = [
        [
            section_title,
            ", ".join(term.title() for term in keywords[:3]) or "Core ideas",
            "Study the concept through definition, flow, and exam relevance rather than line-by-line copying.",
        ]
    ]
    sentence_note = (
        f"{section_title} is best revised as a connected study topic that combines definition, role, flow, examples, "
        "and likely exam framing."
    )
    return {
        "section_id": chunk["section_id"],
        "title": section_title,
        "page_numbers": chunk["page_numbers"],
        "source_excerpt": chunk["raw_text"][:600],
        "topics": [term.title() for term in keywords[:5]] or [section_title],
        "explanation": explanation,
        "key_points": key_points,
        "definitions": definitions,
        "examples": examples,
        "use_cases": use_cases,
        "important_notes": important_notes,
        "why_this_matters": (
            "This section matters because exams typically test whether the learner can explain the concept clearly, "
            "connect it to architecture or workflow, and apply it in context."
        ),
        "common_mistakes": common_mistakes,
        "test_yourself": test_yourself,
        "notes": {
            "cornell": {
                "cue": [
                    f"What problem does {section_title} solve?",
                    f"How would you explain the flow or working of {section_title}?",
                    f"Where can {section_title} appear in an exam answer or application scenario?",
                ],
                "notes": "\n".join(key_points + examples + use_cases[:1]),
                "summary": f"{section_title} should be revised through concept, flow, and application.",
            },
            "outline": {
                "title": section_title,
                "sections": [
                    {"heading": f"{section_title} - Core Idea", "points": key_points[:2]},
                    {"heading": f"{section_title} - Definitions and Use", "points": definitions[:2] + use_cases[:1]},
                    {"heading": f"{section_title} - Exam Notes", "points": important_notes[:2] + common_mistakes[:1]},
                ],
            },
            "mindmap": {
                "root": section_title,
                "mermaid": _mindmap_mermaid(section_title, branches),
                "branches": branches,
            },
            "chart": chart_rows,
            "sentence": sentence_note,
        },
        "diagrams": [],
        "questions": _build_exam_questions(section_title, keywords, definitions),
    }


def _too_similar(source_text: str, generated_text: str) -> bool:
    if not source_text or not generated_text:
        return False
    source = re.sub(r"\s+", " ", source_text.lower())[:2500]
    target = re.sub(r"\s+", " ", generated_text.lower())[:2500]
    return SequenceMatcher(None, source, target).ratio() > 0.82


def _concept_prompt(chunk: dict[str, Any], preferences: dict[str, Any]) -> tuple[str, str]:
    system_prompt = (
        "You are a concept extraction system for academic notes. "
        "Extract the teaching structure from the chunk. "
        "Do not summarize the whole document. "
        "Do not copy long sentences from the source. "
        "Return valid JSON only."
    )
    user_prompt = (
        f"Document title: {preferences['document_title']}\n"
        f"Difficulty target: {preferences['difficulty_level']}\n"
        f"Source pages: {preferences['source_page_count']}\n"
        f"Target note pages: {preferences['target_note_pages']['min']} to {preferences['target_note_pages']['max']}\n"
        f"Exam focus: {preferences['exam_focus']}\n"
        f"Section title hint: {chunk['title']}\n"
        f"Page numbers: {chunk['page_numbers']}\n\n"
        "Tasks:\n"
        "1. Identify the true teaching title for this chunk.\n"
        "2. Extract main topics and sub-concepts.\n"
        "3. Extract useful definitions.\n"
        "4. Extract important relationships between concepts.\n"
        "5. Mention diagram-relevant ideas if the chunk seems architectural, layered, process-based, or flow-based.\n\n"
        f"Chunk text:\n{chunk['raw_text']}"
    )
    return system_prompt, user_prompt


def _section_prompt(
    chunk: dict[str, Any],
    concept_payload: dict[str, Any],
    preferences: dict[str, Any],
    diagram_hints: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = (
        "You are an AI academic note writer in transformation mode.\n"
        "CRITICAL INSTRUCTION:\n"
        "You are NOT allowed to copy sentences from the source text.\n"
        "You MUST rewrite in your own words, simplify where needed, expand where needed, and convert raw material into study notes.\n"
        "If the output is close to the source wording, it is invalid.\n"
        "You are not a summarizer; you are a teacher creating exam-ready study material.\n"
        "Maintain proportional depth: long documents need long, detailed notes rather than one-page summaries.\n"
        "Always produce structured, section-wise notes. Return JSON only."
    )
    diagram_text = json.dumps(diagram_hints, ensure_ascii=True)
    user_prompt = (
        f"Document title: {preferences['document_title']}\n"
        f"Preferred depth: {preferences['note_depth']}\n"
        f"Preferred format emphasis: {preferences['preferred_format']}\n"
        f"Difficulty target: {preferences['difficulty_level']}\n"
        f"Source pages: {preferences['source_page_count']}\n"
        f"Target note pages: {preferences['target_note_pages']['min']} to {preferences['target_note_pages']['max']}\n"
        f"Exam focus: {preferences['exam_focus']}\n"
        f"Include examples: {preferences['include_examples']}\n"
        f"Include diagrams: {preferences['include_diagrams']}\n"
        f"Section pages: {chunk['page_numbers']}\n\n"
        "Mind Map Rules:\n"
        "- Must show hierarchy: root to branch to sub-branch.\n"
        "- Must show relationships, not flat bullets.\n"
        "- Must also provide Mermaid mindmap code.\n\n"
        "Question Rules:\n"
        "- Generate conceptual, theory, application, and MCQ items.\n"
        "- Questions must be exam-oriented and non-generic.\n"
        "- Avoid repetition.\n\n"
        "Diagram Integration Rule:\n"
        "- If diagram hints are present, explain the diagram step by step.\n"
        "- Connect the diagram to the theory.\n"
        "- Produce a simplified Mermaid representation when possible.\n"
        "- If diagrams exist but are ignored, the output is invalid.\n\n"
        f"Structured concept payload:\n{json.dumps(concept_payload, ensure_ascii=True)}\n\n"
        f"Diagram hints:\n{diagram_text}\n\n"
        f"Source chunk:\n{chunk['raw_text']}"
    )
    return system_prompt, user_prompt


def _generate_section_with_llm(
    chunk: dict[str, Any],
    preferences: dict[str, Any],
    diagram_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    concept_system, concept_user = _concept_prompt(chunk, preferences)
    concepts = generate_structured_json(
        concept_system,
        concept_user,
        "section_concepts",
        CONCEPT_SCHEMA,
    )

    section_system, section_user = _section_prompt(chunk, concepts, preferences, diagram_hints)
    generated = generate_structured_json(
        section_system,
        section_user,
        "section_notes",
        SECTION_SCHEMA,
        images=_diagram_images_for_llm(diagram_hints),
    )

    if _too_similar(chunk["raw_text"], generated.get("explanation", "")) or _too_similar(
        chunk["raw_text"],
        generated.get("notes", {}).get("cornell", {}).get("notes", ""),
    ):
        raise ValueError("Generated section stayed too close to source wording.")

    return {
        "section_id": chunk["section_id"],
        "title": generated["title"] or chunk["title"],
        "page_numbers": chunk["page_numbers"],
        "source_excerpt": chunk["raw_text"][:600],
        "topics": concepts.get("topics") or _keywords(chunk["raw_text"], limit=5),
        "explanation": generated["explanation"],
        "key_points": _dedupe(generated["key_points"], limit=6),
        "definitions": _dedupe(generated["definitions"], limit=5),
        "examples": _dedupe(generated["examples"], limit=4),
        "use_cases": _dedupe(generated["use_cases"], limit=4),
        "important_notes": _dedupe(generated["important_notes"], limit=5),
        "why_this_matters": generated["why_this_matters"],
        "common_mistakes": _dedupe(generated["common_mistakes"], limit=4),
        "test_yourself": _dedupe(generated["test_yourself"], limit=4),
        "notes": generated["notes"],
        "diagrams": [],
        "questions": generated["questions"],
    }


def _aggregate_cornell(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    cues = []
    notes = []
    summaries = []
    for section in sections:
        cues.extend(section["notes"]["cornell"]["cue"])
        notes.append(f"{section['title']}\n{section['notes']['cornell']['notes']}")
        summaries.append(section["notes"]["cornell"]["summary"])
    return {
        "title": f"{title} - Cornell Notes",
        "format": "cornell",
        "cue": _dedupe(cues, limit=15),
        "notes": "\n\n".join(notes),
        "summary": " ".join(summaries[:6]),
    }


def _aggregate_outline(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    return {
        "title": f"{title} - Outline",
        "format": "outline",
        "sections": [item for section in sections for item in section["notes"]["outline"]["sections"]],
    }


def _aggregate_mindmap(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    branches = []
    for section in sections:
        branches.append(
            {
                "name": section["title"],
                "sub_branches": section["notes"]["mindmap"]["branches"],
            }
        )
    return {
        "title": f"{title} - Mind Map",
        "format": "mindmap",
        "root": title,
        "mermaid": _mindmap_mermaid(title, branches),
        "branches": branches,
    }


def _aggregate_chart(sections: list[dict[str, Any]], title: str) -> dict[str, Any]:
    rows = []
    for section in sections:
        rows.extend(section["notes"]["chart"])
    return {
        "title": f"{title} - Chart",
        "format": "chart",
        "columns": ["Topic", "Key Idea", "Explanation"],
        "rows": rows,
    }


def _aggregate_sentence(sections: list[dict[str, Any]], title: str, summary: str) -> str:
    paragraphs = [summary]
    paragraphs.extend(section["notes"]["sentence"] for section in sections)
    return "\n\n".join(paragraphs) if sections else f"{title}: {summary}"


def _global_summary(sections: list[dict[str, Any]], title: str) -> str:
    if not sections:
        return f"{title} could not be transformed into study notes."
    return " ".join(
        f"{section['title']}: {section['notes']['cornell']['summary']}"
        for section in sections[:4]
    )


def _collect_diagram_hints(diagrams: list[dict[str, Any]] | None, page_numbers: list[int]) -> list[dict[str, Any]]:
    if not diagrams:
        return []
    hints = []
    page_set = set(page_numbers)
    for diagram in diagrams:
        if diagram.get("page_number") in page_set:
            hints.append(
                {
                    "page_number": diagram.get("page_number"),
                    "caption": diagram.get("caption", ""),
                    "context_text": diagram.get("context_text", ""),
                    "diagram_type": diagram.get("diagram_type", ""),
                    "image_path": diagram.get("image_path", ""),
                }
            )
    return hints[:3]


def _diagram_images_for_llm(diagram_hints: list[dict[str, Any]]) -> list[dict[str, str]]:
    images = []
    for hint in diagram_hints[:2]:
        image_path = hint.get("image_path")
        if not image_path:
            continue
        path = BASE_DIR / image_path
        if not path.exists() or path.stat().st_size > 4_000_000:
            continue
        suffix = path.suffix.lower()
        mime_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        images.append({"image_url": image_bytes_to_data_url(path.read_bytes(), mime_type)})
    return images


def _empty_diagram_mermaid(section_title: str, diagram: dict[str, Any]) -> str:
    label = diagram.get("caption") or section_title
    return "\n".join(
        [
            "flowchart TD",
            f"  A[{section_title}] --> B[{label}]",
            "  B --> C[Key structure or flow]",
            "  C --> D[Exam explanation point]",
        ]
    )


def _enrich_section_diagrams(section: dict[str, Any]) -> None:
    for diagram in section.get("diagrams", []):
        if not diagram.get("caption"):
            diagram["caption"] = f"Relevant diagram for {section['title']}"
        if not diagram.get("explanation"):
            diagram["explanation"] = (
                f"This diagram supports the section on {section['title']}. "
                "Use it to explain the structure, flow, or relationship between the main concepts in your own words."
            )
        if not diagram.get("mermaid_code"):
            diagram["mermaid_code"] = _empty_diagram_mermaid(section["title"], diagram)


def generate_note_package(
    text: str,
    filename: str,
    preferences: dict[str, Any] | None = None,
    extracted_diagrams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned = _clean_text(text)
    title = _title_from_filename(filename)
    difficulty = _difficulty_from_text(cleaned)
    source_page_count = len(_split_pages(cleaned))
    target_note_pages = _target_note_pages(source_page_count)
    pref = {
        "note_depth": (preferences or {}).get("note_depth", "deep"),
        "preferred_format": (preferences or {}).get("preferred_format", "cornell"),
        "exam_focus": bool((preferences or {}).get("exam_focus", True)),
        "include_examples": bool((preferences or {}).get("include_examples", True)),
        "include_diagrams": bool((preferences or {}).get("include_diagrams", True)),
        "document_title": title,
        "difficulty_level": difficulty,
        "source_page_count": source_page_count,
        "target_note_pages": target_note_pages,
    }
    chunks = _chunk_pages(cleaned, filename)

    sections = []
    generation_mode = "llm" if has_llm_support() else "fallback"
    for chunk in chunks:
        diagram_hints = _collect_diagram_hints(extracted_diagrams, chunk["page_numbers"])
        try:
            if has_llm_support():
                section = _generate_section_with_llm(chunk, pref, diagram_hints)
            else:
                raise RuntimeError("LLM support not configured.")
        except Exception:
            generation_mode = "fallback"
            section = _fallback_section(chunk, title)
        sections.append(section)

    summary = _global_summary(sections, title)
    revision = _revision_strategy(len(sections), difficulty)
    package = {
        "document_title": title,
        "source_filename": filename,
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
        "questions": [question for section in sections for question in section.get("questions", [])],
        "global_summary": summary,
        "difficulty_level": difficulty,
        "recommended_revision_strategy": revision,
        "note_volume_policy": {
            "source_pages": source_page_count,
            "target_note_pages": target_note_pages,
            "rule": "Generated notes should preserve proportional depth instead of collapsing the document into a short summary.",
        },
        "preferences": pref,
        "generation_mode": generation_mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    for section in package["sections"]:
        _enrich_section_diagrams(section)
    package["diagrams"] = [diagram for section in package["sections"] for diagram in section.get("diagrams", [])]
    package["questions"] = [question for section in package["sections"] for question in section.get("questions", [])]
    return package


def format_package_for_view(package: dict[str, Any], note_format: str) -> dict[str, Any]:
    note_format = note_format.lower()
    notes = package.get("notes", {})
    if note_format == "full":
        return package
    if note_format in notes:
        return notes[note_format]
    return notes.get("cornell", {})
