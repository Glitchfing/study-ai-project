from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from activity import record_activity
from note_store import get_note_record
from quiz_attempt_store import list_quiz_attempts, save_quiz_attempt

router = APIRouter()

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
        {
            "id": "nlp-2",
            "type": "mcq",
            "question": "Which tokenisation strategy splits unknown words into sub-word units?",
            "options": ["Word-level", "Byte-Pair Encoding (BPE)", "Character-level", "Sentence-Piece"],
            "correct": 1,
            "explanation": "BPE handles out-of-vocabulary terms by representing them as known sub-word fragments.",
            "difficulty": "medium",
            "topic": "NLP",
            "source": "static",
        },
    ],
    "ml": [
        {
            "id": "ml-1",
            "type": "mcq",
            "question": "What criterion does a Decision Tree use to select the best split?",
            "options": ["Mean Squared Error only", "Gini Impurity or Information Gain", "Cross-Entropy Loss", "L2 Regularisation"],
            "correct": 1,
            "explanation": "Tree algorithms select splits that improve purity, commonly using Gini impurity or information gain.",
            "difficulty": "easy",
            "topic": "ML",
            "source": "static",
        },
        {
            "id": "ml-2",
            "type": "mcq",
            "question": "How does Random Forest reduce overfitting compared to a single Decision Tree?",
            "options": ["Deeper trees", "Bagging and feature randomness", "Stronger regularisation loss", "Smaller learning rate"],
            "correct": 1,
            "explanation": "Random Forest averages many decorrelated trees, reducing variance.",
            "difficulty": "medium",
            "topic": "ML",
            "source": "static",
        },
    ],
    "ds": [
        {
            "id": "ds-1",
            "type": "mcq",
            "question": "What is the time complexity of searching in a balanced Binary Search Tree?",
            "options": ["O(n)", "O(log n)", "O(1)", "O(n log n)"],
            "correct": 1,
            "explanation": "A balanced BST keeps height logarithmic, so search is O(log n).",
            "difficulty": "easy",
            "topic": "DS",
            "source": "static",
        },
    ],
}


def _normalize_question(question: dict[str, Any], *, index: int, note_id: str | None, note_title: str, section: dict[str, Any] | None = None) -> dict[str, Any]:
    q_type = question.get("type") or "conceptual"
    options = question.get("options") or []
    answer_index = question.get("answer_index", question.get("correct", 0))
    topic_values = section.get("topics") if section else None
    topic = ", ".join(topic_values[:2]) if isinstance(topic_values, list) and topic_values else note_title

    return {
        "id": question.get("id") or f"{note_id or 'static'}-{index}",
        "note_id": note_id,
        "section_id": section.get("section_id") if section else None,
        "section_title": section.get("title") if section else None,
        "type": q_type,
        "question": question.get("question") or "Untitled question",
        "options": options,
        "correct": int(answer_index or 0),
        "answer_index": int(answer_index or 0),
        "answer_hint": question.get("answer_hint") or "",
        "explanation": question.get("explanation") or question.get("answer_hint") or "Review the related notes section.",
        "difficulty": question.get("difficulty") or "medium",
        "topic": topic,
        "source": "generated" if note_id else question.get("source", "static"),
    }


def _generated_questions_for_note(note_id: str, limit: int) -> dict[str, Any]:
    record = get_note_record(note_id)
    if not record:
        raise HTTPException(status_code=404, detail="Note not found")

    package = record.get("package") or {}
    note_title = record.get("title") or package.get("document_title") or "Generated Note"
    questions = []
    counter = 0
    for section in package.get("sections") or []:
        for question in section.get("questions") or []:
            counter += 1
            questions.append(_normalize_question(question, index=counter, note_id=note_id, note_title=note_title, section=section))

    if not questions:
        for question in package.get("questions") or []:
            counter += 1
            questions.append(_normalize_question(question, index=counter, note_id=note_id, note_title=note_title))

    return {
        "topic": record.get("topic") or "generated",
        "topic_label": note_title,
        "note_id": note_id,
        "note_title": note_title,
        "total": len(questions),
        "questions": questions[:limit],
    }


@router.get("")
def get_quiz(
    topic: str = Query("all"),
    limit: int = Query(5),
    note_id: str | None = Query(None),
):
    if note_id:
        payload = _generated_questions_for_note(note_id, limit)
        record_activity("quiz_started", topic="generated", note_id=note_id, limit=limit)
        return payload

    record_activity("quiz_started", topic=topic.lower(), limit=limit)
    if topic == "all":
        questions = [q for qs in QUIZ_BANK.values() for q in qs]
    else:
        questions = QUIZ_BANK.get(topic.lower(), [])

    import random

    questions = list(questions)
    random.shuffle(questions)
    return {
        "topic": topic,
        "topic_label": topic.upper() if topic != "all" else "Mixed Quiz",
        "note_id": None,
        "note_title": None,
        "total": len(questions),
        "questions": questions[:limit],
    }


@router.post("/attempts")
def create_quiz_attempt(payload: dict[str, Any]):
    responses = payload.get("responses") or []
    if not responses:
        raise HTTPException(status_code=400, detail="No quiz responses supplied.")

    total = int(payload.get("total") or len(responses))
    correct = int(payload.get("correct") or 0)
    score = int(payload.get("score") or round((correct / max(total, 1)) * 100))
    weak_topics = payload.get("weak_topics") or [
        response.get("topic")
        for response in responses
        if not response.get("is_correct") and response.get("topic")
    ]
    weak_topics = list(dict.fromkeys(weak_topics))
    question_types = Counter(response.get("type") or "general" for response in responses)

    attempt = save_quiz_attempt(
        {
            **payload,
            "score": score,
            "total": total,
            "correct": correct,
            "weak_topics": weak_topics,
            "question_types": dict(question_types),
        }
    )

    record_activity(
        "quiz_completed",
        topic=(payload.get("topic") or "generated").lower(),
        topic_label=payload.get("topic_label") or payload.get("note_title") or "Generated Quiz",
        note_id=payload.get("note_id"),
        score=score,
        total=total,
        correct=correct,
        weak_topics=weak_topics,
        attempt_id=attempt["id"],
    )
    return attempt


@router.get("/attempts")
def get_quiz_attempts(note_id: str | None = Query(None), limit: int = Query(20)):
    return {"attempts": list_quiz_attempts(note_id=note_id, limit=limit)}
