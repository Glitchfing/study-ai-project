from __future__ import annotations

import asyncio
import re
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from services.diagram_explainer import connect_diagram_to_notes
from services.document_intelligence import analyze_full_document
from ai_generation import generate_structured_json, has_llm_support
from services.educational_note_generator import (
    generate_human_notes,
    NARRATIVE_NOTE_SCHEMA,
    _section_payload,
)
from services.intelligent_quiz_generator import generate_exam_style_questions
from services.semantic_section_builder import build_semantic_sections


# ============================================================
# ASYNC BRIDGE
# ============================================================

def _run_async_safely(coro):
    """
    Run an async pipeline from both:
      1. normal synchronous Python code
      2. an already-running FastAPI/asyncio event loop

    FastAPI routes may call this module synchronously while the event
    loop is active. Calling asyncio.run() directly in that situation
    raises:
        RuntimeError: asyncio.run() cannot be called from a running event loop

    A small worker thread gives the coroutine its own event loop without
    changing the public synchronous API used by the existing project.
    """
    try:
        asyncio.get_running_loop()
        loop_is_running = True
    except RuntimeError:
        loop_is_running = False

    if not loop_is_running:
        return asyncio.run(coro)

    def runner():
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(runner).result()


# ============================================================
# DOCUMENT-AGNOSTIC SECTION QUALITY
# ============================================================

_GENERIC_SECTION_TITLES = {
    "simple", "type", "types", "advantages", "disadvantages",
    "adv", "dis", "working", "example", "examples", "details",
    "concept", "concepts", "notes", "data", "module",
    "introduction", "overview", "information",
}

_SENTENCE_STARTERS = (
    "here ", "this ", "these ", "those ", "if ", "when ", "because ",
    "which ", "where ", "while ", "although ", "users ", "user ",
    "device ", "devices ", "it ", "they ", "each ", "every ",
)

def _section_title(section: dict[str, Any]) -> str:
    value = (
        section.get("title")
        or section.get("heading")
        or section.get("name")
        or section.get("topic")
        or ""
    )
    value = re.sub(r"\s+", " ", str(value).strip())
    value = re.sub(r"^\s*(?:section|topic)\s+\d+\s*[:.)-]?\s*", "", value, flags=re.I)
    value = re.sub(r"^\s*\d+(?:\.\d+)*\s*[:.)-]?\s*", "", value)
    return value.strip(" :-–—")

def _section_source(section: dict[str, Any]) -> str:
    for key in (
        "raw_text", "source_text", "extracted_text",
        "content", "text", "educational_explanation", "explanation"
    ):
        value = section.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def _is_weak_section_title(title: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()
    if not normalized:
        return True
    if normalized in _GENERIC_SECTION_TITLES:
        return True
    if len(normalized.split()) > 14:
        return True
    if re.search(r"[.!?]$", title):
        return True
    if normalized.startswith(_SENTENCE_STARTERS):
        return True
    return False

def _merge_section_source(target: dict[str, Any], source_section: dict[str, Any]) -> None:
    source = _section_source(source_section)
    if source:
        existing = _section_source(target)
        target["raw_text"] = (
            f"{existing}\n\n{source}" if existing and source not in existing else (existing or source)
        )

    page_values = (
        source_section.get("pages")
        or source_section.get("page_numbers")
        or []
    )
    if isinstance(page_values, int):
        page_values = [page_values]
    if isinstance(page_values, list):
        current = target.get("pages") or target.get("page_numbers") or []
        if isinstance(current, int):
            current = [current]
        target["pages"] = sorted(set(current or []) | set(page_values))

def _prepare_semantic_sections(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Generic second-pass section cleanup.

    It does NOT know any subject-specific terms. It only removes obviously
    sentence-like/generic section labels and attaches their source material
    to the previous meaningful section.
    """
    cleaned: list[dict[str, Any]] = []

    for raw in sections or []:
        if not isinstance(raw, dict):
            continue

        section = dict(raw)
        title = _section_title(section)

        if _is_weak_section_title(title):
            if cleaned:
                _merge_section_source(cleaned[-1], section)
            continue

        section["title"] = title
        source = _section_source(section)
        if source:
            section["raw_text"] = source

        pages = section.get("pages") or section.get("page_numbers") or []
        if isinstance(pages, int):
            pages = [pages]
        section["pages"] = sorted(set(pages)) if isinstance(pages, list) else []

        cleaned.append(section)

    for index, section in enumerate(cleaned, start=1):
        section["section_index"] = index

    print(
        f"[SEMANTIC SECTION QUALITY] "
        f"{len(sections or [])} raw -> {len(cleaned)} usable"
    )
    return cleaned


# ============================================================
# DIAGRAM HELPERS
# ============================================================


def _normalize_semantic_sections(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Backward-compatible wrapper around the generic semantic section cleaner.
    """
    return _prepare_semantic_sections(sections)


def _diagrams_for_section(
    section: dict[str, Any],
    diagrams: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Return diagrams that belong to the current section.

    Matching is based on:
    - source filename
    - page number

    Maximum 4 diagrams are attached to one section.
    """

    if not diagrams:
        return []

    page_numbers = set(
        section.get("page_numbers")
        or section.get("pages")
        or []
    )
    source_filename = (
        section.get("source_filename")
        or section.get("filename")
    )

    return [
        diagram
        for diagram in diagrams
        if (
            not source_filename
            or not diagram.get("source_filename")
            or diagram.get("source_filename") == source_filename
        )
        and (
            not page_numbers
            or diagram.get("page_number") in page_numbers
        )
    ][:4]


# ============================================================
# DOCUMENT INTELLIGENCE
# ============================================================

def run_document_analysis(
    text: str,
    filename: str,
    *,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Analyze the complete document once.

    This determines:
    - document title
    - major topics
    - topic relationships
    - learning structure
    - revision priority
    """

    return analyze_full_document(
        text,
        filename,
        diagrams=diagrams,
        preferences=preferences,
    )


# ============================================================
# SEQUENTIAL NOTE GENERATION
# ============================================================

def run_note_generation(
    text: str,
    filename: str,
    intelligence: dict[str, Any],
    *,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Sequential version.

    Kept as a fallback/debugging option.
    Production pipeline uses run_note_generation_async().
    """

    sections = build_semantic_sections(
        text,
        intelligence,
        filename,
    )

    sections = _normalize_semantic_sections(sections)

    generated_sections = []

    for section in sections:

        diagram_context = _diagrams_for_section(
            section,
            diagrams,
        )

        notes = generate_human_notes(
            section,
            intelligence,
            preferences=preferences,
            diagram_context=diagram_context,
        )

        enriched_diagrams = [
            connect_diagram_to_notes(
                dict(diagram),
                {
                    **section,
                    **notes,
                },
            )
            for diagram in diagram_context
        ]

        generated_sections.append(
            {
                **section,
                **notes,
                "diagrams": enriched_diagrams,
                "questions": [],
            }
        )

    return generated_sections


# ============================================================
# PARALLEL NOTE GENERATION
# ============================================================

async def run_note_generation_async(
    text: str,
    filename: str,
    intelligence: dict[str, Any],
    *,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate notes with content-aware multi-section batching.

    Design goals:
      - 5-7 related sections per LLM request when the source is small enough.
      - Never merge sections in the returned package.
      - Keep source text grounded and page-aware.
      - Control output volume using a per-section word budget.
      - Use at most two batch requests concurrently by default.
      - Do NOT explode a failed batch into many extra LLM calls.
    """

    sections = build_semantic_sections(
        text,
        intelligence,
        filename,
    )

    sections = _normalize_semantic_sections(sections)

    if not sections:
        return []

    # --------------------------------------------------------
    # Batch configuration
    # --------------------------------------------------------
    max_sections = max(
        2,
        int(os.getenv("NOTE_BATCH_MAX_SECTIONS", "7")),
    )

    max_source_words = max(
        1200,
        int(os.getenv("NOTE_BATCH_MAX_SOURCE_WORDS", "5500")),
    )

    max_parallel_batches = max(
        1,
        int(os.getenv("NOTE_BATCH_CONCURRENCY", "2")),
    )

    # Maximum output tokens for ONE batch. This prevents a single
    # unusually large request from consuming the entire provider budget.
    max_output_tokens = max(
        1500,
        int(os.getenv("NOTE_BATCH_MAX_OUTPUT_TOKENS", "7000")),
    )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def section_words(section: dict[str, Any]) -> int:
        return max(
            1,
            len(
                re.findall(
                    r"\w+",
                    str(section.get("raw_text") or ""),
                )
            ),
        )

    def section_terms(section: dict[str, Any]) -> set[str]:
        values: list[str] = []

        for key in (
            "title",
            "concept_group",
            "related_topics",
            "concept_keywords",
        ):
            value = section.get(key)
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            elif value:
                values.append(str(value))

        return {
            token
            for token in re.findall(
                r"[a-z0-9+#-]{3,}",
                " ".join(values).lower(),
            )
            if token
            not in {
                "the", "and", "for", "with", "from", "this",
                "that", "section", "topic", "using", "used",
                "types", "type", "basic", "introduction",
                "overview", "notes",
            }
        }

    def semantic_related(
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> bool:
        left_terms = section_terms(left)
        right_terms = section_terms(right)

        if not left_terms or not right_terms:
            return False

        return bool(
            left_terms.intersection(right_terms)
        )

    def make_batches(
        source_sections: list[dict[str, Any]],
    ) -> list[list[tuple[str, dict[str, Any]]]]:
        """
        Build contiguous, size-aware batches.

        Contiguous ordering is intentional: adjacent educational sections
        are generally safer to group than arbitrary distant sections.
        """

        batches: list[list[tuple[str, dict[str, Any]]]] = []
        current: list[tuple[str, dict[str, Any]]] = []
        current_words = 0
        current_terms: set[str] = set()

        for index, section in enumerate(
            source_sections,
            start=1,
        ):
            section_id = f"section_{index}"
            words = section_words(section)
            terms = section_terms(section)

            if not current:
                current = [(section_id, section)]
                current_words = words
                current_terms = set(terms)
                continue

            exceeds_sections = (
                len(current) >= max_sections
            )

            exceeds_words = (
                current_words + words
                > max_source_words
            )

            overlap = bool(
                current_terms.intersection(terms)
            )

            # Do not force a semantically distant section into a
            # large batch once we already have several sections.
            unrelated = (
                not overlap
                and len(current) >= 4
            )

            if (
                exceeds_sections
                or exceeds_words
                or unrelated
            ):
                batches.append(current)
                current = [(section_id, section)]
                current_words = words
                current_terms = set(terms)
            else:
                current.append(
                    (section_id, section)
                )
                current_words += words
                current_terms.update(terms)

        if current:
            batches.append(current)

        return batches

    batches = make_batches(sections)

    print(
        f"\n[NOTE BATCHING] "
        f"{len(sections)} sections -> "
        f"{len(batches)} LLM batches"
    )

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        titles = [
            str(section.get("title") or "Untitled")
            for _, section in batch
        ]
        words = sum(
            section_words(section)
            for _, section in batch
        )

        print(
            f"[NOTE BATCH {batch_number}] "
            f"{len(batch)} sections | "
            f"{words} source words | "
            f"{' | '.join(titles)}"
        )

    # --------------------------------------------------------
    # Batch response schema
    # --------------------------------------------------------
    batch_item_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "section_id": {"type": "string"},
            **NARRATIVE_NOTE_SCHEMA.get(
                "properties",
                {},
            ),
        },
        "required": [
            "section_id",
            *NARRATIVE_NOTE_SCHEMA.get(
                "required",
                [],
            ),
        ],
    }

    batch_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sections": {
                "type": "array",
                "items": batch_item_schema,
            },
        },
        "required": ["sections"],
    }

    # --------------------------------------------------------
    # Local fallback
    # --------------------------------------------------------
    def local_fallback(
        section: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Deterministic fallback used when all LLM providers fail.

        IMPORTANT:
        The fallback preserves the existing study-note contract used by
        the frontend. It must not reduce a section to raw source text only.

        The fallback reuses the grounded rule-based study-aid extractor
        from educational_note_generator.py, so the existing UI sections
        remain populated even when Groq/Gemini are unavailable or rate
        limited. No additional LLM request is made here.
        """

        title = (
            section.get("title")
            or "Study Topic"
        )

        raw = str(
            section.get("raw_text")
            or ""
        ).strip()

        diagram_context = _diagrams_for_section(
            section,
            diagrams,
        )

        content = raw

        # Keep fallback content readable without creating an
        # unnecessarily huge single card.
        if len(content) > 9000:
            content = (
                content[:9000]
                .rsplit(" ", 1)[0]
                + "..."
            )

        # --------------------------------------------------------
        # IMPORTANT:
        # Reuse the existing deterministic study-aid builder.
        # This preserves the fields consumed by the current frontend:
        # definitions, exam/key points, examples, revision, etc.
        # --------------------------------------------------------
        try:
            from services.educational_note_generator import (
                _fallback_study_aids,
            )

            fallback_aids = _fallback_study_aids(
                section,
                title,
                content,
            )

        except Exception as fallback_error:
            print(
                "[FALLBACK STUDY AIDS ERROR] "
                f"{type(fallback_error).__name__}: "
                f"{fallback_error}"
            )

            # Extremely defensive fallback. The normal path above
            # should populate these fields from source text.
            fallback_aids = {
                "key_points": [],
                "definitions": [],
                "examples": [],
                "use_cases": [],
                "important_notes": [],
                "why_this_matters": "",
                "common_mistakes": [],
                "revision_notes": [],
                "memory_tricks": [],
                "concept_comparisons": [],
                "test_yourself": [],
            }

        # --------------------------------------------------------
        # Keep the existing frontend contract.
        # Do NOT replace these fields with note_structure.
        # note_structure is additive metadata only.
        # --------------------------------------------------------
        payload = {
            "title": title,
            "content": content,
            "key_points": fallback_aids.get(
                "key_points", []
            ),
            "definitions": fallback_aids.get(
                "definitions", []
            ),
            "examples": fallback_aids.get(
                "examples", []
            ),
            "use_cases": fallback_aids.get(
                "use_cases", []
            ),
            "important_notes": fallback_aids.get(
                "important_notes", []
            ),
            "why_this_matters": fallback_aids.get(
                "why_this_matters", ""
            ),
            "common_mistakes": fallback_aids.get(
                "common_mistakes", []
            ),
            "revision_notes": fallback_aids.get(
                "revision_notes", []
            ),
            "memory_tricks": fallback_aids.get(
                "memory_tricks", []
            ),
            "concept_comparisons": fallback_aids.get(
                "concept_comparisons", []
            ),
            "test_yourself": fallback_aids.get(
                "test_yourself", []
            ),
        }

        # --------------------------------------------------------
        # Additive adaptive structure.
        # This does not replace the old UI segmentation.
        # --------------------------------------------------------
        payload["note_structure"] = {
            "structure_type": "source_based",
            "blocks": [
                {
                    "heading": title,
                    "block_type": "explanation",
                    "content": content,
                    "items": [],
                    "columns": [],
                    "rows": [],
                }
            ],
        }

        notes = _section_payload(
            section,
            title,
            content,
            diagram_context,
            payload,
        )

        # `_section_payload()` intentionally maps the established
        # frontend fields. Preserve the new adaptive structure
        # explicitly because it is additive metadata.
        notes["note_structure"] = payload[
            "note_structure"
        ]

        enriched_diagrams = [
            connect_diagram_to_notes(
                dict(diagram),
                {**section, **notes},
            )
            for diagram in diagram_context
        ]

        print(
            f"[NOTE FALLBACK COMPLETE] "
            f"{title} | "
            f"key_points={len(notes.get('key_points') or [])} | "
            f"definitions={len(notes.get('definitions') or [])} | "
            f"examples={len(notes.get('examples') or [])} | "
            f"revision={len(notes.get('revision_notes') or [])}"
        )

        return {
            **section,
            **notes,
            "diagrams": enriched_diagrams,
            "questions": [],
        }

    # --------------------------------------------------------
    # Generate ONE batch
    # --------------------------------------------------------
    def generate_batch(
        batch: list[tuple[str, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        if not has_llm_support():
            return [
                local_fallback(section)
                for _, section in batch
            ]

        compact_intelligence = {
            "document_title": intelligence.get(
                "document_title"
            ),
            "major_topics": intelligence.get(
                "major_topics",
                [],
            ),
            "subtopics": intelligence.get(
                "subtopics",
                [],
            ),
            "relationships": intelligence.get(
                "concept_relationships",
                [],
            ),
            "revision_order": intelligence.get(
                "revision_priority_order",
                [],
            ),
        }

        batch_payload = []

        for section_id, section in batch:
            raw = str(
                section.get("raw_text")
                or ""
            ).strip()

            source_words = section_words(
                section
            )

            # Adaptive compression:
            # short sections retain more detail;
            # large sections are compressed more strongly.
            if source_words <= 350:
                ratio = 0.65
            elif source_words <= 800:
                ratio = 0.58
            elif source_words <= 1500:
                ratio = 0.52
            else:
                ratio = 0.45

            target_words = min(
                850,
                max(
                    220,
                    round(source_words * ratio),
                ),
            )

            diagram_context = _diagrams_for_section(
                section,
                diagrams,
            )

            batch_payload.append(
                {
                    "section_id": section_id,
                    "title": section.get(
                        "title"
                    ) or "Study Topic",
                    "page_numbers": section.get(
                        "page_numbers"
                    ) or section.get(
                        "pages"
                    ) or [],
                    "target_words": target_words,
                    "diagram_context": diagram_context,
                    "source_text": raw,
                }
            )

        system_prompt = """
You are the study-note generation engine for an educational AI system.

You are generating MULTIPLE independent study-note sections in one
API request.

CORE GOAL:
Maximize useful learning value per word. The result must be concise
enough that a student will actually study it, but complete enough to
retain the important academic content.

STRICT SOURCE RULES:
1. Use the supplied source as the primary authority.
2. Do not invent facts, formulas, examples, applications, steps,
   definitions, or claims.
3. Preserve source-specific terminology.
4. Rewrite for clarity; do not copy long source sentences.
5. Do not turn every sentence into a separate point.
6. Remove repetition, filler, generic introductions, and redundant
   explanations.
7. Preserve important definitions, mechanisms, procedures, formulas,
   comparisons, examples, applications, diagrams, and exam-relevant
   distinctions when present.
8. If a source contains a useful process, preserve the complete process.
9. If a source contains a useful diagram, explain what it represents
   and how it connects to the topic.
10. Do not create content merely to make the notes longer.

SECTION RULES:
11. Return exactly one result for every supplied section_id.
12. Keep every section separate.
13. Never move information between sections.
14. Do not merge section titles.
15. Respect target_words as a strong output-size target, not an excuse
    to remove important information.
16. Prefer dense, meaningful notes over verbose teaching prose.
17. Use note_structure adaptively when the schema supports it.
18. Return ONLY valid JSON.
""".strip()

        user_prompt = (
            "DOCUMENT INTELLIGENCE:\n"
            f"{json.dumps(compact_intelligence, ensure_ascii=True)}\n\n"
            "STUDENT NOTE POLICY:\n"
            f"{json.dumps(preferences or {}, ensure_ascii=True)}\n\n"
            "SECTIONS:\n"
            f"{json.dumps(batch_payload, ensure_ascii=True)}\n\n"
            "For each section, produce the standard note fields: "
            "title, content, key_points, definitions, examples, "
            "use_cases, important_notes, why_this_matters, "
            "common_mistakes, revision_notes, memory_tricks, "
            "concept_comparisons, test_yourself, and note_structure "
            "when that field exists in the supplied schema."
        )

        print(
            f"[BATCH LLM START] "
            f"{len(batch)} sections"
        )

        generated = generate_structured_json(
            system_prompt,
            user_prompt,
            "teaching_narrative_batch",
            batch_schema,
            temperature=0.28,
            cache=False,
            max_output_tokens=max_output_tokens,
        )

        result = generated.get(
            "sections"
        ) or []

        if len(result) != len(batch):
            raise ValueError(
                "Batch LLM returned an incorrect "
                "number of sections: "
                f"expected {len(batch)}, "
                f"got {len(result)}"
            )

        by_id = {
            str(item.get("section_id")): item
            for item in result
            if isinstance(item, dict)
        }

        output = []

        for section_id, section in batch:
            generated_item = by_id.get(
                section_id
            )

            if not generated_item:
                raise ValueError(
                    f"Batch LLM omitted {section_id}."
                )

            title = str(
                generated_item.get("title")
                or section.get("title")
                or "Study Topic"
            ).strip()

            content = str(
                generated_item.get("content")
                or ""
            ).strip()

            if not content:
                raise ValueError(
                    f"Batch LLM returned empty "
                    f"content for {section_id}."
                )

            diagram_context = _diagrams_for_section(
                section,
                diagrams,
            )

            notes = _section_payload(
                section,
                title,
                content,
                diagram_context,
                generated_item,
            )

            enriched_diagrams = [
                connect_diagram_to_notes(
                    dict(diagram),
                    {**section, **notes},
                )
                for diagram in diagram_context
            ]

            output.append(
                {
                    **section,
                    **notes,
                    "diagrams": enriched_diagrams,
                    "questions": [],
                }
            )

        print(
            f"[BATCH LLM DONE] "
            f"{len(output)} sections"
        )

        return output

    # --------------------------------------------------------
    # Controlled parallelism
    # --------------------------------------------------------
    semaphore = asyncio.Semaphore(
        max_parallel_batches
    )

    async def run_one_batch(
        batch: list[tuple[str, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        async with semaphore:
            try:
                return await asyncio.to_thread(
                    generate_batch,
                    batch,
                )

            except Exception as exc:
                print(
                    "\n[BATCH GENERATION ERROR]"
                    f"\nType: {type(exc).__name__}"
                    f"\nMessage: {exc}"
                    "\nUsing local fallback for this batch."
                )

                return [
                    local_fallback(section)
                    for _, section in batch
                ]

    batch_results = await asyncio.gather(
        *[
            run_one_batch(batch)
            for batch in batches
        ]
    )

    final_sections: list[dict[str, Any]] = []

    for batch in batch_results:
        final_sections.extend(batch)

    return final_sections


# ============================================================
# REVISION GENERATION
# ============================================================

def run_revision_generation(
    package: dict[str, Any],
) -> dict[str, Any]:

    sections = package.get("sections") or []

    order = (
        package
        .get("document_intelligence", {})
        .get("revision_priority_order")
        or [
            section.get("title")
            for section in sections
        ]
    )

    return {
        "revision_priority_order": order,

        "strategy": (
            "Use a 1-3-7 day cycle. "
            "First revise concept flow, then redraw diagrams, "
            "then answer scenario and comparison questions."
        ),

        "daily_plan": [
            (
                f"Revise {title}: "
                "definition, workflow, example, mistake, "
                "and one question."
            )
            for title in order[:10]
            if title
        ],
    }


# ============================================================
# QUIZ GENERATION
# ============================================================

def run_quiz_generation(
    package: dict[str, Any],
    *,
    limit: int = 12,
    memory: list[str] | None = None,
) -> list[dict[str, Any]]:

    return generate_exam_style_questions(
        package,
        limit=limit,
        memory=memory,
    )


# ============================================================
# COMPLETE MULTI-PASS PIPELINE
# ============================================================

def run_multi_pass_pipeline(
    text: str,
    filename: str,
    *,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
    quiz_limit: int = 12,
) -> dict[str, Any]:
    """
    Complete study-note generation pipeline:

        Document
            ↓
        Document Intelligence
            ↓
        Semantic Sections
            ↓
        Parallel AI Teaching Notes
            ↓
        Revision Strategy
            ↓
        Quiz
            ↓
        Final Study Package

    Note generation is executed asynchronously with
    a maximum of 3 concurrent LLM requests.
    """

    # ========================================================
    # PASS 1 — FULL DOCUMENT UNDERSTANDING
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )
    print(
        "PASS 1: DOCUMENT INTELLIGENCE"
    )
    print(
        "=" * 80
    )

    intelligence = run_document_analysis(
        text,
        filename,
        diagrams=diagrams,
        preferences=preferences,
    )

    # ========================================================
    # PASS 2 — SEMANTIC SECTIONS + AI NOTES
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )
    print(
        "PASS 2: PARALLEL NOTE GENERATION"
    )
    print(
        "=" * 80
    )

    sections = _run_async_safely(
        run_note_generation_async(
            text,
            filename,
            intelligence,
            diagrams=diagrams,
            preferences=preferences,
        )
    )

    # ========================================================
    # BUILD STUDY PACKAGE
    # ========================================================

    # Final defensive cleanup after generation. This prevents an LLM
    # response from reintroducing an obviously generic/sentence-like
    # section title while keeping all valid educational content.
    sections = _prepare_semantic_sections(sections)

    # ========================================================
    # BUILD STUDY PACKAGE
    # ========================================================
    #
    # IMPORTANT:
    # `sections` contains only diagrams that were matched to
    # individual sections. The original diagnostic test also
    # expects the complete extracted diagram collection to be
    # available at the package level.
    #
    # Previously:
    #
    #     PDF -> extract 2 diagrams
    #          -> attach to sections
    #          -> package had no top-level "diagrams"
    #          -> diagnostic reported Diagrams: 0
    #
    # We therefore preserve BOTH:
    #   1. section-level diagrams
    #   2. the complete document-level diagram list
    #
    # This does NOT duplicate image data in the extraction
    # stage or call Vision again. It only preserves the
    # already-extracted diagram metadata in the final package.
    #

    package = {
        "document_title": (
            intelligence.get("document_title")
            or filename
        ),

        "source_filename": filename,

        "document_intelligence": intelligence,

        "topic_map": intelligence,

        "sections": sections,

        # COMPLETE EXTRACTED DIAGRAM COLLECTION
        "diagrams": list(diagrams or []),
    }

    # ========================================================
    # PASS 3 — REVISION
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )
    print(
        "PASS 3: REVISION STRATEGY"
    )
    print(
        "=" * 80
    )

    package["revision"] = run_revision_generation(
        package
    )

    # ========================================================
    # PASS 4 — QUIZ
    # ========================================================

    print(
        "\n"
        + "=" * 80
    )
    print(
        "PASS 4: QUIZ GENERATION"
    )
    print(
        "=" * 80
    )

    package["questions"] = run_quiz_generation(
        package,
        limit=quiz_limit,
    )

    return package


# ============================================================
# TARGETED TOPIC NOTE PIPELINE
# ============================================================

def run_targeted_note_pipeline(
    context: str,
    topic: str,
    *,
    source_metadata: dict[str, Any] | None = None,
    diagrams: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
    quiz_limit: int = 8,
) -> dict[str, Any]:
    """
    Generate study notes and quiz questions exclusively for a requested topic
    from retrieved source context chunks (without re-processing the whole book).

    Flow:
        Retrieved Chunks Context
                 ↓
        Scoped Topic Intelligence
                 ↓
        Focused Semantic Sections
                 ↓
        Parallel Teaching Notes
                 ↓
        Targeted Revision Strategy
                 ↓
        Targeted Quiz Questions
    """
    metadata = source_metadata or {}
    filename = metadata.get("filename") or "Targeted Source"
    pages = metadata.get("pages") or []
    headings = metadata.get("headings") or []
    clean_topic = topic.strip() or "Requested Topic"

    pages_str = ", ".join(str(p) for p in pages) if pages else "retrieved sections"
    summary_text = (
        f"Focused study notes on '{clean_topic}', retrieved from source pages ({pages_str}) "
        f"of {filename}."
    )

    clean_headings = [h for h in headings if h and h.lower() != clean_topic.lower() and len(h) >= 3]
    if clean_headings:
        major_topics = [clean_topic] + clean_headings[:5]
    else:
        major_topics = [clean_topic]

    intelligence = {
        "document_title": f"{clean_topic} — Targeted Study",
        "major_topics": major_topics,
        "subtopics": clean_headings,
        "concept_relationships": [f"{clean_topic} -> {h}" for h in clean_headings[:5]],
        "revision_priority_order": [clean_topic] + clean_headings[:4],
        "document_summary": summary_text,
        "source_quality": {"usable_sections": True, "targeted": True},
        "analysis_mode": "llm" if has_llm_support() else "fallback",
    }

    pref = dict(preferences or {})
    pref.setdefault("note_depth", "deep")
    pref.setdefault("preferred_format", "cornell")
    pref.setdefault("target_topic", clean_topic)
    pref["educational_depth_policy"] = (
        f"You are generating targeted study material strictly for the topic: '{clean_topic}'. "
        "The supplied context represents only the relevant sections retrieved from the uploaded document, "
        "not the complete document. Use only the supplied source material without inventing missing facts. "
        "Preserve definitions, mechanisms, examples, formulas, comparisons, and source terminology."
    )

    print("\n" + "=" * 80)
    print(f"TARGETED PIPELINE: '{clean_topic}' ({len(pages)} source pages, {len(context.split())} words)")
    print("=" * 80)

    sections = _run_async_safely(
        run_note_generation_async(
            context,
            filename,
            intelligence,
            diagrams=diagrams,
            preferences=pref,
        )
    )

    sections = _prepare_semantic_sections(sections)

    package = {
        "document_title": f"{clean_topic} — Targeted Study",
        "source_filename": filename,
        "requested_topic": clean_topic,
        "document_intelligence": intelligence,
        "topic_map": intelligence,
        "sections": sections,
        "diagrams": list(diagrams or []),
        "retrieval": {
            "document_id": metadata.get("document_id"),
            "pages": pages,
            "headings": headings,
            "retrieved_chunks": metadata.get("retrieved_chunks", len(sections)),
            "context_word_count": metadata.get("context_word_count", len(context.split())),
        },
    }

    package["revision"] = run_revision_generation(package)
    package["questions"] = run_quiz_generation(package, limit=quiz_limit)
    return package