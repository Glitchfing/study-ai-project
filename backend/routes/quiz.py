from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    UploadFile,
    File,
)

from activity import record_activity
from note_store import get_note_record, get_saved_quiz_set, save_quiz_set
from note_generation import generate_note_package
from quiz_engine import evaluate_answer, generate_quiz_for_package, performance_feedback
from services.targeted_retrieval_service import retrieve_targeted_chunks
from quiz_attempt_store import (
    list_quiz_attempts,
    save_quiz_attempt,
)
from session_store import attach_quiz_attempt, find_session_by_note_id

import json
import uuid
import random

from pathlib import Path

from pypdf import PdfReader
from docx import Document

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

GENERATED_NOTES_DIR = Path("generated_notes")
GENERATED_NOTES_DIR.mkdir(exist_ok=True)

QUIZ_BANK = {
    "nlp": [
        {
            "id": "nlp-1",
            "type": "mcq",
            "question": "What does BERT stand for?",
            "options": [
                "Bidirectional Encoder Representations from Transformers",
                "Binary Encoded Recurrent Transformer",
                "Basic Encoding and Retrieval Technique",
                "Bidirectional Embedding Recurrent Tokeniser",
            ],
            "correct": 0,
            "explanation": "BERT uses bidirectional transformer encoder representations trained with masked language modelling.",
            "difficulty": "easy",
            "topic": "NLP",
            "source": "static",
        },
    ],
}


# =====================================================
# DOCUMENT TEXT EXTRACTION
# =====================================================

def extract_text(file_path: str) -> str:
    path = Path(file_path)

    if path.suffix == ".pdf":
        reader = PdfReader(file_path)

        pages = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()

            pages.append(f"[[PAGE_{index}]]\n{page_text or ''}")

        return "\n\n".join(pages)

    if path.suffix == ".docx":
        doc = Document(file_path)

        return "\n".join(
            [p.text for p in doc.paragraphs]
        )

    if path.suffix == ".txt":
        return Path(file_path).read_text(
            encoding="utf-8"
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type",
    )


# =====================================================
# GROQ AI GENERATION
# =====================================================

def generate_ai_content(document_text: str, filename: str):
    return generate_note_package(
        document_text,
        filename,
        preferences={
            "note_depth": "deep",
            "preferred_format": "cornell",
            "exam_focus": True,
            "include_examples": True,
            "include_diagrams": True,
        },
    )


# =====================================================
# DOCUMENT UPLOAD ROUTE
# =====================================================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):

    note_id = str(uuid.uuid4())

    file_path = (
        UPLOAD_DIR /
        f"{note_id}_{file.filename}"
    )

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    extracted_text = extract_text(
        str(file_path)
    )

    ai_package = generate_ai_content(extracted_text, file.filename or "uploaded-document.txt")

    note_record = {
        "id": note_id,
        "title": file.filename,
        "topic": "generated",
        "package": ai_package,
    }

    with open(
        GENERATED_NOTES_DIR / f"{note_id}.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            note_record,
            f,
            indent=2,
        )

    return {
        "message": "AI notes generated successfully",
        "note_id": note_id,
        "summary": ai_package.get("global_summary"),
        "topics": [
            topic.get("title") if isinstance(topic, dict) else str(topic)
            for topic in (ai_package.get("topic_map") or {}).get("major_topics", [])
            if (topic.get("title") if isinstance(topic, dict) else str(topic))
        ],
    }


# =====================================================
# QUESTION NORMALIZER
# =====================================================

def _normalize_question(
    question: dict[str, Any],
    *,
    index: int,
    note_id: str | None,
    note_title: str,
    section: dict[str, Any] | None = None,
) -> dict[str, Any]:

    q_type = question.get("type") or "conceptual"

    options = question.get("options") or []

    answer_index = question.get(
        "answer_index",
        question.get("correct", 0),
    )

    topic_values = (
        section.get("topics")
        if section
        else None
    )

    # Prefer an explicit topic from the question generator. Section titles are
    # a fallback only, so topic-level mastery does not accidentally fragment
    # into section-title buckets.
    topic = (
        str(question.get("topic")).strip()
        if isinstance(question.get("topic"), str) and question.get("topic").strip()
        else ", ".join(topic_values[:2])
        if isinstance(topic_values, list) and topic_values
        else note_title
    )

    return {
        "id": question.get("id")
        or f"{note_id or 'static'}-{index}",

        "note_id": note_id,

        "section_id": (
            section.get("section_id")
            if section
            else None
        ),

        "section_title": (
            section.get("title")
            if section
            else None
        ),

        "type": q_type,

        "question": (
            question.get("question")
            or "Untitled question"
        ),

        "options": options,

        "correct": int(answer_index or 0),

        "answer_index": int(answer_index or 0),

        "answer_hint": (
            question.get("answer_hint")
            or ""
        ),

        "explanation": (
            question.get("explanation")
            or question.get("answer_hint")
            or "Review the related notes section."
        ),

        "difficulty": (
            question.get("difficulty")
            or "medium"
        ),

        "topic": topic,

        # Concept tags are supplied by the question generator. Do not infer an
        # exact sub-concept from a topic or section title when no tag exists.
        "concept_id": question.get("concept_id") or question.get("concept") or question.get("concept_tag") or None,

        "source": (
            "generated"
            if note_id
            else question.get("source", "static")
        ),
    }


# =====================================================
# GENERATED QUESTIONS
# =====================================================

def _retrieve_quiz_evidence(
    record: dict[str, Any],
    topic: str | None = None,
    package_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build quiz context from Qdrant chunks restricted to this note's source documents."""
    # Callers may hydrate legacy/static notes from their rendered content. Preserve
    # that recovery instead of re-reading the empty original package here.
    package = dict(package_override or record.get("package") or {})
    document_ids = package.get("source_document_ids") or record.get("source_document_ids") or []
    document_ids = [str(value).strip() for value in document_ids if str(value).strip()]
    if not document_ids:
        return {"package": package, "retrieved_chunks": 0, "source_document_ids": []}

    note_title = str(record.get("title") or package.get("document_title") or "Study note")
    requested_topic = (topic or package.get("requested_quiz_topic") or "").strip()
    existing_sections = package.get("sections") or []
    queries = [requested_topic] if requested_topic else []
    if not requested_topic:
        for section in existing_sections:
            title = str(section.get("title") or "").strip()
            topics = section.get("topics") or []
            for candidate in [title, *(topics if isinstance(topics, list) else [])]:
                candidate = str(candidate).strip()
                if candidate and candidate.lower() not in {q.lower() for q in queries}:
                    queries.append(candidate)
        if not queries:
            queries = [note_title]

    gathered: dict[str, dict[str, Any]] = {}
    for document_id in document_ids:
        for query in queries[:20]:
            try:
                result = retrieve_targeted_chunks(
                    document_id=document_id,
                    query=query,
                    top_k=6 if requested_topic else 4,
                    max_chunks=8 if requested_topic else 4,
                )
            except Exception:
                continue
            for match in result.get("matches") or []:
                key = str(match.get("chunk_id") or (document_id, match.get("page"), match.get("text")))
                previous = gathered.get(key)
                if previous is None or float(match.get("score") or 0) > float(previous.get("score") or 0):
                    gathered[key] = match

    matches = sorted(
        gathered.values(),
        key=lambda item: (str(item.get("document_id") or ""), int(item.get("page") or 0), int(item.get("chunk_index") or 0)),
    )
    if not matches:
        # If this note already contains a quiz generated with the exact same
        # topic, prefer that persisted quiz instead of failing because Qdrant
        # is temporarily unavailable or its chunks cannot be retrieved.
        saved_topic = str(
            package.get("requested_quiz_topic")
            or package.get("requested_topic")
            or ""
        ).strip()
        same_saved_scope = (
            not topic
            or (
                bool(saved_topic)
                and " ".join(topic.lower().split()) == " ".join(saved_topic.lower().split())
            )
        )
        saved_questions = package.get("questions") or []
        if same_saved_scope and isinstance(saved_questions, list) and saved_questions:
            package["quiz_topic"] = saved_topic or "entire note"
            return {
                "package": package,
                "retrieved_chunks": 0,
                "source_document_ids": document_ids,
            }
        raise HTTPException(
            status_code=404,
            detail="No indexed source chunks were retrieved for this topic, and no saved quiz matches it. Verify Qdrant indexing or choose the note's original topic.",
        )

    grouped: dict[str, list[str]] = {}
    for match in matches:
        heading = str(match.get("heading") or f"Page {match.get('page') or '?'}").strip()
        text = str(match.get("text") or "").strip()
        if text:
            grouped.setdefault(heading, []).append(text)
    package["sections"] = [
        {
            "section_id": f"rag-{index}",
            "title": heading,
            "topics": [heading],
            "content": "\n\n".join(dict.fromkeys(parts)),
            "educational_explanation": "\n\n".join(dict.fromkeys(parts)),
            "key_points": list(dict.fromkeys(parts)),
        }
        for index, (heading, parts) in enumerate(grouped.items(), start=1)
    ]
    package["document_title"] = note_title
    package["quiz_source"] = "qdrant_rag"
    package["quiz_topic"] = requested_topic or "entire note"
    package["retrieved_source_text"] = "\n\n".join(str(match.get("text") or "") for match in matches)
    return {"package": package, "retrieved_chunks": len(matches), "source_document_ids": document_ids}


def _generated_questions_for_note(
    note_id: str,
    limit: int,
    topic: str | None = None,
) -> dict[str, Any]:

    record = get_note_record(note_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Note not found",
        )

    package = dict(record.get("package") or {})

    note_title = (
        record.get("title")
        or package.get("document_title")
        or "Generated Note"
    )

    # Persisted quiz sets are note- and topic-specific. Reuse them across
    # refreshes; if they are short, merge them with new candidates below.
    requested_scope = str(
        topic
        or package.get("requested_quiz_topic")
        or package.get("requested_topic")
        or ""
    ).strip()
    cached_quiz = get_saved_quiz_set(note_id, requested_scope)
    if cached_quiz:
        cached_questions = cached_quiz.get("questions") or []
        if len(cached_questions) >= max(1, limit):
            return {
                "topic": record.get("topic") or "generated",
                "topic_label": note_title,
                "note_id": note_id,
                "note_title": note_title,
                "total": min(len(cached_questions), max(1, limit)),
                "retrieval": {
                    "mode": "saved_quiz_cache",
                    "retrieved_chunks": 0,
                    "source_document_ids": package.get("source_document_ids") or record.get("source_document_ids") or [],
                },
                "questions": cached_questions[:max(1, limit)],
            }
        # Seed top-up generation with the valid saved questions, while still
        # allowing the source-backed generator to find additional candidates.
        package["questions"] = [
            *(package.get("questions") or []),
            *cached_questions,
        ]

    # Static notes may store their real learning content in the rendered formats
    # rather than package.sections. Promote that source text into a section so the
    # question generator never sees only a title and an empty package.
    if not package.get("sections"):
        content = record.get("content") or {}
        cornell = content.get("cornell") or {}
        source_text = cornell.get("notes") or cornell.get("summary") or ""
        if not source_text:
            outline = content.get("outline") or {}
            outline_sections = outline.get("sections") or []
            source_text = "\n\n".join(
                str(section.get("heading") or "") + "\n" +
                "\n".join(str(point) for point in (section.get("points") or []))
                for section in outline_sections
            )
        if source_text.strip():
            package["sections"] = [{
                "section_id": f"{note_id}-source",
                "title": note_title,
                "topics": [note_title],
                "content": source_text,
                "educational_explanation": source_text,
                "key_points": [line.strip() for line in source_text.splitlines() if len(line.split()) >= 5],
            }]

    rag = _retrieve_quiz_evidence(record, topic=topic, package_override=package)
    package = rag["package"]

    # Saved synthesized notes may not have indexed source-document IDs, so
    # RAG setup can return early. Preserve a user-requested topic either way.
    if topic and str(topic).strip():
        package["quiz_topic"] = str(topic).strip()
    questions = generate_quiz_for_package(
        package,
        note_id=note_id,
        note_title=note_title,
        limit=limit,
    )
    final_scope = str(
        topic
        or package.get("requested_quiz_topic")
        or package.get("requested_topic")
        or ""
    ).strip()
    if questions:
        save_quiz_set(note_id, final_scope, questions)

    return {
        "topic": (
            record.get("topic")
            or "generated"
        ),

        "topic_label": note_title,

        "note_id": note_id,

        "note_title": note_title,

        "total": len(questions),
        "retrieval": {"mode": "qdrant_rag" if rag["retrieved_chunks"] else "saved_note_fallback", "retrieved_chunks": rag["retrieved_chunks"], "source_document_ids": rag["source_document_ids"]},
        "questions": questions,
    }


# =====================================================
# QUIZ ROUTE
# =====================================================

@router.get("")
def get_quiz(
    topic: str = Query("all"),
    limit: int = Query(5),
    note_id: str | None = Query(None),
    quiz_topic: str | None = Query(None, description="Optional topic to retrieve from the selected note"),
):

    if note_id:

        payload = _generated_questions_for_note(
            note_id,
            limit,
            topic=quiz_topic,
        )

        record_activity(
            "quiz_started",
            topic="generated",
            note_id=note_id,
            limit=limit,
        )

        return payload

    record_activity(
        "quiz_started",
        topic=topic.lower(),
        limit=limit,
    )

    if quiz_topic and quiz_topic.strip():
        # For static quizzes, honor the requested topic across the available
        # bank and return no questions rather than silently giving an unrelated quiz.
        requested = " ".join(quiz_topic.lower().split())
        all_questions = [question for rows in QUIZ_BANK.values() for question in rows]
        questions = [
            question for question in all_questions
            if requested in " ".join([
                str(question.get("topic") or ""),
                str(question.get("question") or ""),
                str(question.get("explanation") or ""),
            ]).lower()
        ]
    elif topic == "all":
        questions = [
            q
            for qs in QUIZ_BANK.values()
            for q in qs
        ]
    else:
        questions = QUIZ_BANK.get(
            topic.lower(),
            [],
        )

    questions = list(questions)

    random.shuffle(questions)

    return {
        "topic": topic,

        "topic_label": (
            quiz_topic.strip()
            if quiz_topic and quiz_topic.strip()
            else topic.upper()
            if topic != "all"
            else "Mixed Quiz"
        ),

        "note_id": None,

        "note_title": None,

        "total": len(questions),

        "questions": questions[:limit],
    }


# =====================================================
# QUIZ ATTEMPTS
# =====================================================

@router.post("/attempts")
def create_quiz_attempt(
    payload: dict[str, Any]
):

    responses = (
        payload.get("responses")
        or []
    )

    if not responses:
        raise HTTPException(
            status_code=400,
            detail="No quiz responses supplied.",
        )

    evaluated_responses = []
    for response in responses:
        question_payload = response.get("question_data") or response
        if response.get("question_data"):
            evaluation = evaluate_answer(question_payload, response)
            evaluated_responses.append({**response, **evaluation})
        else:
            evaluated_responses.append(response)

    responses = evaluated_responses
    total = int(payload.get("total") or len(responses))
    correct = sum(1 for response in responses if response.get("is_correct"))
    score = int(round((correct / max(total, 1)) * 100))
    performance = performance_feedback(correct, total)

    weak_topics = [
        response.get("topic")
        for response in responses
        if not response.get("is_correct")
        and response.get("topic")
    ]

    weak_topics = list(
        dict.fromkeys(weak_topics)
    )

    question_types = Counter(
        response.get("type") or "general"
        for response in responses
    )

    attempt = save_quiz_attempt(
        {
            **payload,
            "score": score,
            "total": total,
            "correct": correct,
            "responses": responses,
            "weak_topics": weak_topics,
            "question_types": dict(question_types),
            "performance": performance,
        }
    )

    attach_quiz_attempt(payload.get("note_id"), attempt, performance)

    recommendation_outcome = None
    recommendation_id = payload.get("recommendation_id")
    if recommendation_id:
        # Link this intervention to its actual saved quiz result. The outcome
        # helper only compares concept/topic responses when their tags match.
        from recommendation_store import record_recommendation_outcome
        recommendation_outcome = record_recommendation_outcome(str(recommendation_id), attempt)

    record_activity(
        "quiz_completed",
        topic=(
            payload.get("topic")
            or "generated"
        ).lower(),

        topic_label=(
            payload.get("topic_label")
            or payload.get("note_title")
            or "Generated Quiz"
        ),

        note_id=payload.get("note_id"),

        score=score,

        total=total,

        correct=correct,

        weak_topics=weak_topics,

        attempt_id=attempt["id"],
        recommendation_id=str(recommendation_id) if recommendation_id else None,
        performance=performance,
    )

    return {
        **attempt,
        "performance": performance,
        "recommendation_outcome": recommendation_outcome,
        "session": find_session_by_note_id(payload.get("note_id")),
    }


# =====================================================
# QUIZ ATTEMPTS HISTORY
# =====================================================

@router.get("/attempts")
def get_quiz_attempts(
    note_id: str | None = Query(None),
    limit: int = Query(20),
):

    return {
        "attempts": list_quiz_attempts(
            note_id=note_id,
            limit=limit,
        )
    }
