from __future__ import annotations

import random
import re
from difflib import SequenceMatcher
from typing import Any

from quiz_attempt_store import list_quiz_attempts
from semantic_utils import cosine_similarity, keyword_overlap
from services.intelligent_quiz_generator import (
    detect_duplicate_questions,
    generate_exam_style_questions,
    rank_question_quality,
)

ALLOWED_TYPES = {
    "mcq",
    "true_false",
    "fill_blank",
    "one_word",
    "sentence",
    "scenario",
    "match",
    "compare",
    "workflow",
    "architecture",
    "case_study",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_answer(value: Any) -> str:
    text = _clean(value).lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _initialism(value: str) -> str:
    words = [word for word in _normalize_answer(value).split() if word]
    return "".join(word[0] for word in words) if len(words) > 1 else ""


def _question_memory(note_id: str | None) -> list[str]:
    if not note_id:
        return []
    memory: list[str] = []
    for attempt in list_quiz_attempts(note_id=note_id, limit=12):
        for response in attempt.get("responses") or []:
            question = response.get("question") or response.get("question_text")
            if question:
                memory.append(question)
    return memory[-120:]


def _keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]+", text.lower())
    stopwords = {"the", "and", "for", "with", "that", "this", "from", "into", "what", "which", "where", "when", "why", "how", "are", "was", "were", "has", "have", "had", "can", "will", "should", "would", "could", "you", "your", "is", "as", "of", "to", "in", "on", "by", "or", "a", "an"}
    counts: dict[str, int] = {}
    for word in words:
        if len(word) <= 2 or word in stopwords:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def _normalize_question(question: dict[str, Any], index: int, note_id: str | None, note_title: str) -> dict[str, Any]:
    q_type = str(question.get("type") or "scenario").lower().replace("-", "_")
    if q_type not in ALLOWED_TYPES:
        q_type = "mcq" if question.get("options") else "scenario"

    options = [_clean(option) for option in question.get("options") or [] if _clean(option)]
    correct_answer = _clean(question.get("correct_answer") or question.get("answer") or "")

    if q_type == "true_false":
        options = ["True", "False"]
        correct_answer = "True" if _normalize_answer(correct_answer) in {"true", "t", "yes", "1"} else "False"

    if q_type == "mcq":
        if correct_answer and correct_answer not in options:
            options = [correct_answer] + [option for option in options if option != correct_answer]
        while len(options) < 4:
            options.append(f"Conceptual distractor {len(options) + 1}")
        options = options[:4]

    acceptable = [_clean(item) for item in question.get("acceptable_answers") or [] if _clean(item)]
    if correct_answer:
        acceptable.append(correct_answer)
        initial = _initialism(correct_answer)
        if initial:
            acceptable.append(initial)

    correct_index = 0
    if options:
        normalized_correct = _normalize_answer(correct_answer)
        correct_index = next(
            (index for index, option in enumerate(options) if _normalize_answer(option) == normalized_correct),
            0,
        )

    return {
        "id": question.get("id") or f"{note_id or 'generated'}-{index}",
        "note_id": note_id,
        "section_id": question.get("section_id"),
        "section_title": question.get("section_title"),
        "type": q_type,
        "question": _clean(question.get("question") or "Untitled question"),
        "options": options,
        "correct": correct_index,
        "answer_index": correct_index,
        "correct_answer": correct_answer or (options[correct_index] if options else ""),
        "acceptable_answers": list(dict.fromkeys(acceptable)),
        "expected_keywords": question.get("expected_keywords") or _keywords(f"{correct_answer} {question.get('explanation', '')}", 6),
        "answer_hint": question.get("answer_hint") or correct_answer,
        "explanation": question.get("explanation") or "Review the related synthesized notes section.",
        "difficulty": question.get("difficulty") or "medium",
        "topic": question.get("topic") or question.get("section_title") or note_title,
        "quality_score": question.get("quality_score") or rank_question_quality(question),
        "source": "generated" if note_id else question.get("source", "static"),
    }


def _shuffle_options(question: dict[str, Any]) -> dict[str, Any]:
    if not question.get("options"):
        return question
    correct_answer = question.get("correct_answer") or question["options"][question.get("correct", 0)]
    options = list(question["options"])
    random.shuffle(options)
    normalized_correct = _normalize_answer(correct_answer)
    correct_index = next((idx for idx, option in enumerate(options) if _normalize_answer(option) == normalized_correct), 0)
    return {**question, "options": options, "correct": correct_index, "answer_index": correct_index}


def _dedupe_after_normalization(questions: list[dict[str, Any]], limit: int, memory: list[str]) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for question in sorted(questions, key=lambda item: item.get("quality_score", 0), reverse=True):
        if any(detect_duplicate_questions(question, previous) for previous in accepted):
            continue
        if any(detect_duplicate_questions(question, previous) for previous in memory):
            continue
        accepted.append(question)
        if len(accepted) >= limit:
            break
    return accepted


def generate_quiz_for_package(
    package: dict[str, Any],
    *,
    note_id: str | None,
    note_title: str,
    limit: int,
) -> list[dict[str, Any]]:
    requested_limit = max(1, limit)
    memory = _question_memory(note_id)
    raw_questions = generate_exam_style_questions(package, limit=max(requested_limit * 2, requested_limit + 6), memory=memory)
    normalized = [
        _normalize_question(question, index=index, note_id=note_id, note_title=note_title)
        for index, question in enumerate(raw_questions, start=1)
    ]
    filtered = _dedupe_after_normalization(normalized, requested_limit, memory)
    if len(filtered) < requested_limit:
        for question in normalized:
            if len(filtered) >= requested_limit:
                break
            if not any(detect_duplicate_questions(question, old) for old in filtered):
                filtered.append(question)
    return [_shuffle_options(question) for question in filtered[:requested_limit]]


def evaluate_answer(question: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    options = question.get("options") or []
    expected_values = list(question.get("acceptable_answers") or [])
    expected_values.append(question.get("correct_answer") or "")
    expected_keywords = [_normalize_answer(keyword) for keyword in question.get("expected_keywords") or [] if _clean(keyword)]

    if options and response.get("selected_index") is not None:
        selected_index = int(response.get("selected_index"))
        selected_answer = options[selected_index] if 0 <= selected_index < len(options) else ""
        is_correct = selected_index == int(question.get("correct", 0))
    else:
        selected_answer = response.get("selected_answer") or response.get("answer") or ""
        normalized_selected = _normalize_answer(selected_answer)
        expected_normalized = [_normalize_answer(value) for value in expected_values if _clean(value)]
        expected_normalized.extend(_initialism(value) for value in expected_values if _initialism(value))
        expected_normalized = [value for value in expected_normalized if value]

        exact_or_close = normalized_selected in expected_normalized or any(
            SequenceMatcher(None, normalized_selected, expected).ratio() >= 0.86
            for expected in expected_normalized
        )
        vector_score = max(
            [cosine_similarity(normalized_selected, expected, expand=True) for expected in expected_normalized]
            or [0]
        )
        overlap_score = max(
            [keyword_overlap(normalized_selected, expected) for expected in expected_normalized]
            or [0]
        )
        keyword_hits = sum(
            1 for keyword in expected_keywords if keyword and (keyword in normalized_selected or keyword in normalized_selected.split())
        )
        keyword_score = keyword_hits / max(len(expected_keywords), 1) if expected_keywords else 0
        is_correct = exact_or_close or vector_score >= 0.68 or (overlap_score >= 0.5 and keyword_score >= 0.34) or keyword_score >= 0.6

    return {
        "is_correct": bool(is_correct),
        "selected_answer": _clean(selected_answer),
        "expected_answer": question.get("correct_answer") or "",
        "expected_keywords": question.get("expected_keywords") or [],
        "semantic_score": round(
            max(
                [cosine_similarity(_normalize_answer(selected_answer), _normalize_answer(value), expand=True) for value in expected_values if _clean(value)]
                or [0]
            ),
            3,
        ),
    }


def performance_feedback(correct: int, total: int) -> dict[str, Any]:
    score_20 = round((correct / max(total, 1)) * 20)
    percentage = round((correct / max(total, 1)) * 100)
    if score_20 >= 18:
        emoji, feedback, motivation = "🥳", "Very Good", "Excellent work. Keep revising with mixed questions to stay sharp."
    elif score_20 >= 15:
        emoji, feedback, motivation = "😄", "Good", "Nice progress. Review the missed points once and try a shuffled quiz."
    elif score_20 >= 10:
        emoji, feedback, motivation = "🥺", "Better Next Time", "You are close. Re-read weak topics and answer them in your own words."
    elif score_20 >= 5:
        emoji, feedback, motivation = "😦", "You Can Do Much Better", "Slow down, revise the basics, and retry with short answers first."
    else:
        emoji, feedback, motivation = "😞", "Do Hard Work", "Start again from the summary notes, then practice the easiest questions."
    return {
        "score_20": score_20,
        "percentage": percentage,
        "emoji": emoji,
        "feedback": feedback,
        "motivational_text": motivation,
    }
