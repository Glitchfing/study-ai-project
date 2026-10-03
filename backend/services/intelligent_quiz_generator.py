from __future__ import annotations

import json
import random
import re
from difflib import SequenceMatcher
from typing import Any

from ai_generation import generate_structured_json, has_llm_support
from semantic_utils import cosine_similarity, keyword_overlap, top_keywords

QUIZ_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_answer": {"type": "string"},
                    "acceptable_answers": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"},
                    "difficulty": {"type": "string"},
                    "topic": {"type": "string"},
                    "expected_keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "type",
                    "question",
                    "options",
                    "correct_answer",
                    "acceptable_answers",
                    "explanation",
                    "difficulty",
                    "topic",
                    "expected_keywords",
                ],
            },
        }
    },
    "required": ["questions"],
}

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
    return " ".join(str(value or "").split())


def _question_text(question: dict[str, Any]) -> str:
    return _clean(f"{question.get('question', '')} {question.get('topic', '')}")


def detect_duplicate_questions(left: dict[str, Any] | str, right: dict[str, Any] | str) -> bool:
    left_text = _question_text(left) if isinstance(left, dict) else _clean(left)
    right_text = _question_text(right) if isinstance(right, dict) else _clean(right)
    if not left_text or not right_text:
        return False
    lexical = SequenceMatcher(None, left_text.lower(), right_text.lower()).ratio()
    semantic = cosine_similarity(left_text, right_text, expand=True)
    overlap = keyword_overlap(left_text, right_text)
    return lexical >= 0.78 or semantic >= 0.72 or overlap >= 0.68


def _section_payload(package: dict[str, Any]) -> list[dict[str, Any]]:
    payload = []
    for section in package.get("sections") or []:
        payload.append(
            {
                "section_id": section.get("section_id"),
                "title": section.get("title"),
                "topics": section.get("topics") or [],
                "content": section.get("content") or section.get("educational_explanation") or section.get("explanation"),
                "explanation": section.get("explanation"),
                "key_points": section.get("key_points") or [],
                "definitions": section.get("definitions") or [],
                "examples": section.get("examples") or [],
                "use_cases": section.get("use_cases") or [],
                "common_mistakes": section.get("common_mistakes") or [],
                "revision_notes": section.get("revision_notes") or [],
                "concept_comparisons": section.get("concept_comparisons") or [],
            }
        )
    return payload


def rank_question_quality(question: dict[str, Any]) -> float:
    text = _question_text(question)
    q_type = str(question.get("type") or "").lower()
    difficulty = str(question.get("difficulty") or "").lower()
    score = 0.0
    if q_type in {"scenario", "case_study", "workflow", "architecture", "compare"}:
        score += 2.2
    elif q_type in {"mcq", "sentence", "match"}:
        score += 1.3
    if difficulty == "hard":
        score += 1.2
    elif difficulty == "medium":
        score += 0.9
    if re.search(r"\bwhy|how|compare|scenario|flow|workflow|architecture|case|apply|reason|mistake|best explains\b", text, re.I):
        score += 1.6
    if re.search(r"\bwhat is\b", text, re.I):
        score -= 1.0
    if len(question.get("expected_keywords") or []) >= 2:
        score += 0.6
    if question.get("options") and len(question.get("options") or []) == 4:
        score += 0.4
    return round(score, 3)


def _difficulty_targets(limit: int) -> list[str]:
    easy = max(1, round(limit * 0.2))
    medium = max(1, round(limit * 0.5))
    hard = max(1, limit - easy - medium)
    values = ["easy"] * easy + ["medium"] * medium + ["hard"] * hard
    while len(values) < limit:
        values.append("medium")
    return values[:limit]


def _fallback_candidates(package: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    candidates = []
    sections = package.get("sections") or []
    difficulties = _difficulty_targets(max(limit * 2, 8))
    for index, section in enumerate(sections):
        title = section.get("title") or "Study Topic"
        keywords = top_keywords(
            f"{title} {section.get('explanation', '')} {' '.join(section.get('key_points') or [])}",
            limit=8,
        )
        focus = keywords[0].title() if keywords else title
        relation = (keywords[1].title() if len(keywords) > 1 else title)
        mistake = (section.get("common_mistakes") or [f"confusing {focus} with a related idea"])[0]
        example = (section.get("examples") or [f"an applied situation involving {focus}"])[0]
        difficulty = difficulties[index % len(difficulties)]
        candidates.extend(
            [
                {
                    "type": "mcq",
                    "question": f"Which explanation best shows how {focus} functions inside {title}?",
                    "options": [
                        f"It connects the purpose of {title} with {relation} and the working flow.",
                        f"It is only a term to memorize without relationships.",
                        f"It matters only when page numbers are asked.",
                        f"It replaces the need to explain examples or workflow.",
                    ],
                    "correct_answer": f"It connects the purpose of {title} with {relation} and the working flow.",
                    "acceptable_answers": [focus, relation],
                    "explanation": f"A strong answer links {focus}, {relation}, and the actual working of {title}.",
                    "difficulty": difficulty,
                    "topic": title,
                    "expected_keywords": [focus, relation, "workflow"],
                },
                {
                    "type": "scenario",
                    "question": f"A learner can define {focus} but cannot solve an application question on {title}. What should they add to their answer?",
                    "options": [],
                    "correct_answer": f"They should add the working flow, relationship with {relation}, and a practical example.",
                    "acceptable_answers": ["workflow", relation, "example", "application"],
                    "explanation": "Application answers need concept use, not definition recall alone.",
                    "difficulty": "hard",
                    "topic": title,
                    "expected_keywords": ["workflow", relation, "example"],
                },
                {
                    "type": "workflow",
                    "question": f"State the correct learning flow for explaining {title} in one sentence.",
                    "options": [],
                    "correct_answer": f"Begin with purpose, explain {focus}, connect it to {relation}, then support it with a use case.",
                    "acceptable_answers": ["purpose", focus, relation, "use case"],
                    "explanation": "The expected flow is purpose, concept, relationship, and application.",
                    "difficulty": "medium",
                    "topic": title,
                    "expected_keywords": ["purpose", focus, relation],
                },
                {
                    "type": "compare",
                    "question": f"Compare {focus} and {relation} using purpose and role in {title}.",
                    "options": [],
                    "correct_answer": f"{focus} should be explained by its role, while {relation} should be linked as the supporting or connected concept.",
                    "acceptable_answers": [focus, relation, "role", "purpose"],
                    "explanation": "Comparison questions test whether the learner can separate roles instead of listing terms.",
                    "difficulty": "medium",
                    "topic": title,
                    "expected_keywords": [focus, relation, "role"],
                },
                {
                    "type": "sentence",
                    "question": f"Rewrite this mistake as a correct exam point: {mistake}",
                    "options": [],
                    "correct_answer": f"A correct answer should explain {title} through concept, working, relationship, and example.",
                    "acceptable_answers": [title, focus, "working", "example"],
                    "explanation": f"The mistake is repaired by adding conceptual explanation and application: {example}",
                    "difficulty": "hard",
                    "topic": title,
                    "expected_keywords": [focus, "working", "example"],
                },
            ]
        )
    if not candidates:
        candidates.append(
            {
                "type": "scenario",
                "question": "A student memorizes the document but cannot explain how ideas connect. What revision method fixes this?",
                "options": [],
                "correct_answer": "Build a concept flow with definitions, relationships, workflow, example, and self-test questions.",
                "acceptable_answers": ["concept flow", "relationships", "workflow", "example"],
                "explanation": "The platform prioritizes connected conceptual revision over memorized summaries.",
                "difficulty": "medium",
                "topic": package.get("document_title") or "Study Session",
                "expected_keywords": ["relationships", "workflow", "example"],
            }
        )
    return candidates


def _llm_candidates(package: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    system_prompt = (
        "You are a university exam setter. Generate varied, non-repetitive, application-focused questions from study notes. "
        "Avoid shallow definition recall and avoid template phrasing. Use plausible distractors. Return JSON only."
    )
    user_prompt = (
        f"Document title: {package.get('document_title')}\n"
        f"Need {max(limit * 2, limit + 8)} candidate questions before filtering.\n"
        "Distribution target after filtering: 20% easy, 50% medium, 30% hard.\n"
        "Required types: conceptual MCQ, scenario, workflow, architecture, case-study, fill_blank, match, one-sentence reasoning, compare-and-contrast, practical application.\n"
        "Rules:\n"
        "- Questions must test understanding, application, reasoning, relationships, workflows, or architecture.\n"
        "- MCQs require exactly four options and realistic misconceptions.\n"
        "- Keep sentence answers concise.\n"
        "- Include expected_keywords for semantic grading.\n"
        "- Do not use repeated stems or generic wording.\n\n"
        f"Document intelligence:\n{json.dumps(package.get('document_intelligence') or package.get('topic_map') or {}, ensure_ascii=True)}\n\n"
        f"Synthesized note sections:\n{json.dumps(_section_payload(package), ensure_ascii=True)[:90000]}"
    )
    payload = generate_structured_json(system_prompt, user_prompt, "intelligent_quiz", QUIZ_SCHEMA, temperature=0.32)
    return payload.get("questions") or []


def detect_concept_overlap(question: dict[str, Any], accepted: list[dict[str, Any]]) -> bool:
    topic = str(question.get("topic") or "").lower()
    expected = " ".join(question.get("expected_keywords") or [])
    for item in accepted:
        if topic and topic == str(item.get("topic") or "").lower():
            if keyword_overlap(expected, " ".join(item.get("expected_keywords") or [])) > 0.62:
                return True
    return False


def _normalize_question(question: dict[str, Any], index: int) -> dict[str, Any]:
    q_type = str(question.get("type") or "scenario").lower().replace("-", "_")
    if q_type not in ALLOWED_TYPES:
        q_type = "mcq" if question.get("options") else "scenario"
    options = [_clean(option) for option in question.get("options") or [] if _clean(option)]
    correct_answer = _clean(question.get("correct_answer") or question.get("answer") or "")
    if q_type == "mcq":
        if correct_answer and correct_answer not in options:
            options = [correct_answer] + options
        options = (options + ["A plausible misconception", "A partial explanation", "An unrelated detail"])[:4]
    if q_type == "true_false":
        options = ["True", "False"]
    return {
        "id": question.get("id") or f"candidate-{index}",
        "type": q_type,
        "question": _clean(question.get("question") or "Untitled question"),
        "options": options,
        "correct_answer": correct_answer or (options[0] if options else ""),
        "acceptable_answers": list(dict.fromkeys([_clean(item) for item in question.get("acceptable_answers") or [] if _clean(item)] + ([correct_answer] if correct_answer else []))),
        "explanation": _clean(question.get("explanation") or "Review the related concept in the notes."),
        "difficulty": str(question.get("difficulty") or "medium").lower(),
        "topic": _clean(question.get("topic") or "Study Topic"),
        "expected_keywords": list(dict.fromkeys([_clean(item) for item in question.get("expected_keywords") or [] if _clean(item)]))[:6],
        "quality_score": rank_question_quality(question),
    }


def _select_diverse(candidates: list[dict[str, Any]], limit: int, memory: list[str] | None = None) -> list[dict[str, Any]]:
    memory = memory or []
    normalized = [_normalize_question(question, index) for index, question in enumerate(candidates, start=1)]
    normalized.sort(key=rank_question_quality, reverse=True)
    target_difficulties = _difficulty_targets(limit)
    selected: list[dict[str, Any]] = []
    topic_counts: dict[str, int] = {}

    for target_difficulty in target_difficulties:
        for question in normalized:
            if question in selected:
                continue
            if question["difficulty"] != target_difficulty and len(selected) < limit // 2:
                continue
            topic_key = question["topic"].lower()
            if topic_counts.get(topic_key, 0) >= 3:
                continue
            if any(detect_duplicate_questions(question, old) for old in selected):
                continue
            if any(detect_duplicate_questions(question, old) for old in memory):
                continue
            if detect_concept_overlap(question, selected) and len(selected) >= max(2, limit // 2):
                continue
            selected.append(question)
            topic_counts[topic_key] = topic_counts.get(topic_key, 0) + 1
            break

    for question in normalized:
        if len(selected) >= limit:
            break
        if any(detect_duplicate_questions(question, old) for old in selected):
            continue
        selected.append(question)
    return selected[:limit]


def generate_conceptual_questions(package: dict[str, Any], limit: int, memory: list[str] | None = None) -> list[dict[str, Any]]:
    return generate_exam_style_questions(package, limit=limit, memory=memory)


def generate_scenario_questions(package: dict[str, Any], limit: int, memory: list[str] | None = None) -> list[dict[str, Any]]:
    questions = generate_exam_style_questions(package, limit=max(limit * 2, limit), memory=memory)
    return [question for question in questions if question["type"] in {"scenario", "case_study", "workflow", "architecture"}][:limit]


def generate_exam_style_questions(
    package: dict[str, Any],
    *,
    limit: int,
    memory: list[str] | None = None,
) -> list[dict[str, Any]]:
    candidate_limit = max(limit * 3, limit + 10)
    if has_llm_support():
        try:
            candidates = _llm_candidates(package, candidate_limit)
        except Exception:
            candidates = _fallback_candidates(package, candidate_limit)
    else:
        candidates = _fallback_candidates(package, candidate_limit)
    selected = _select_diverse(candidates, limit, memory=memory)
    random.shuffle(selected)
    return selected
