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
                    "concept_id": {"type": "string"},
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
                    "concept_id",
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


def _compact_section_payload(package: dict[str, Any], max_chars: int = 18000) -> list[dict[str, Any]]:
    """Keep representative note content in the prompt without exceeding provider token limits."""
    selected: list[dict[str, Any]] = []
    used = 0
    for section in _section_payload(package):
        compact = {
            "title": section.get("title"),
            "topics": section.get("topics") or [],
            "content": section.get("content") or "",
            "key_points": section.get("key_points") or [],
            "definitions": section.get("definitions") or [],
            "examples": section.get("examples") or [],
        }
        serialized = json.dumps(compact, ensure_ascii=True)
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(serialized) > remaining:
            if selected:
                continue
            compact["content"] = str(compact.get("content") or "")[:max(1000, remaining // 2)]
            compact["key_points"] = (compact.get("key_points") or [])[:4]
            serialized = json.dumps(compact, ensure_ascii=True)
        if len(serialized) <= remaining:
            selected.append(compact)
            used += len(serialized)
    return selected


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
    """
    Conservative fallback: build a question only when the note provides a
    specific concept and enough source-grounded distractors. Never manufacture
    generic questions from the document title or pad missing options.
    """
    sections = package.get("sections") or []
    facts: list[dict[str, str]] = []
    for section in sections:
        title = _clean(section.get("title") or package.get("document_title") or "Study topic")
        sources = [
            *(section.get("definitions") or []),
            *(section.get("key_points") or []),
            *(section.get("revision_notes") or []),
            *(section.get("concept_comparisons") or []),
        ]
        for source in sources:
            if isinstance(source, dict):
                fact = _clean(source.get("definition") or source.get("description") or source.get("point") or source.get("text") or source.get("explanation"))
                concept = _clean(source.get("term") or source.get("concept") or source.get("title") or "")
            else:
                fact, concept = _clean(source), ""
            if (
                concept
                and concept.lower() != title.lower()
                and len(fact.split()) >= 5
                and not any(item["fact"].lower() == fact.lower() for item in facts)
            ):
                facts.append({"topic": title, "concept": concept, "fact": fact})

    # Synthesized notes commonly store the actual facts as prose rather than
    # structured definitions. Extract complete source sentences so fallback
    # generation still works when the provider is unavailable or returns invalid JSON.
    for section in sections:
        title = _clean(section.get("title") or package.get("document_title") or "Study topic")
        source_text = _clean(
            section.get("content")
            or section.get("educational_explanation")
            or section.get("explanation")
            or ""
        )
        for sentence in re.split(r"(?<=[.!?])\\s+|[\\n•]+", source_text):
            fact = _clean(sentence).strip(" •-–—")
            words = fact.split()
            if len(words) < 7 or not fact:
                continue
            concept = fact.split(":", 1)[0].strip() if ":" in fact else " ".join(words[:4])
            concept = concept.strip(" .,:;!?-–—")
            if not concept or concept.lower() == title.lower():
                concept = " ".join(words[:4]).strip(" .,:;!?-–—")
            if not any(item["fact"].lower() == fact.lower() for item in facts):
                facts.append({"topic": title, "concept": concept, "fact": fact})

    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(facts):
        distractors = [
            other["fact"] for j, other in enumerate(facts)
            if j != index and other["fact"].lower() != item["fact"].lower()
        ]
        if len(distractors) < 3:
            continue
        options = [item["fact"], *random.sample(distractors, 3)]
        options = list(dict.fromkeys(options))
        if len(options) != 4:
            continue
        random.shuffle(options)
        stems = [
            f"Which statement most accurately describes {item['concept']}?",
            f"Which option correctly explains the role of {item['concept']}?",
            f"When applying the concept of {item['concept']}, which statement is supported by the notes?",
            f"Which statement distinguishes {item['concept']} from related concepts in the notes?",
        ]
        candidates.append({
            "type": "mcq",
            "question": stems[index % len(stems)],
            "options": options,
            "correct_answer": item["fact"],
            "acceptable_answers": [item["fact"]],
            "explanation": f"The selected statement matches the notes' description of {item['concept']} in '{item['topic']}'.",
            "difficulty": ["easy", "medium", "hard"][index % 3],
            "topic": item["topic"],
            "concept_id": item["concept"],
            "expected_keywords": top_keywords(item["fact"], limit=6),
        })
        if len(candidates) >= max(limit * 3, limit + 10):
            break
    return candidates


def _llm_candidates(package: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    system_prompt = (
        "You are a university exam setter. Generate ONLY four-option multiple-choice questions (MCQs) directly grounded in the supplied study notes. "
        "Write a real exam-style MCQ quiz, not short-answer prompts and not one-sentence answer exercises. "
        "Use a mix of conceptual understanding, application, scenario-based reasoning, and comparisons when supported by the notes. "
        "Every question must test a specific fact, concept, relationship, or application supported by the source notes. "
        "Never ask generic study-skills questions, never use the document title as a substitute for subject content, and never invent unsupported facts. "
        "Each question must have a meaningful question stem, exactly four distinct answer options, one unambiguous correct option, and a concise explanation. "
        "Distractors must be plausible misconceptions related to the same subject, not placeholders or unrelated sentences. Return JSON only."
    )
    user_prompt = (
        f"Document title: {package.get('document_title')}\n"
        f"Requested quiz topic: {package.get('quiz_topic') or 'entire note'}\n"
        "When a topic is specified, every question must test that topic and be answerable from the retrieved source evidence.\n"
        f"Need {limit} candidate questions before filtering.\n"
        "Distribution target after filtering: 20% easy, 50% medium, 30% hard.\n"
        "Required type: mcq only. Every question must have exactly four non-empty options and exactly one correct option.\n"
        "Rules:\n"
        "- Return MCQs only, each with exactly four distinct options and one correct answer.\n"
        "- Use only information supported by the supplied notes; do not create generic questions.\n"
        "- If the source lacks enough information, return fewer questions rather than guessing.\n"
        "- Include expected_keywords for semantic grading.\n"
        "- Set concept_id to a concise, specific concept tested by the question; reuse the same name for the same concept across questions. Do not use the document title unless it is itself the concept.\n"
        "- Do not use repeated stems or generic wording.\n\n"
        f"Document intelligence:\n{json.dumps(package.get('document_intelligence') or package.get('topic_map') or {}, ensure_ascii=True)}\n\n"
        f"Synthesized note sections:\n{json.dumps(_compact_section_payload(package), ensure_ascii=True)}"
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
    """Normalize a validated MCQ without inventing options or answers."""
    options = list(dict.fromkeys(_clean(option) for option in question.get("options") or [] if _clean(option)))
    correct_answer = _clean(question.get("correct_answer") or question.get("answer") or "")
    return {
        "id": question.get("id") or f"candidate-{index}",
        "type": "mcq",
        "question": _clean(question.get("question") or ""),
        "options": options,
        "correct_answer": correct_answer,
        "acceptable_answers": list(dict.fromkeys([_clean(item) for item in question.get("acceptable_answers") or [] if _clean(item)] + ([correct_answer] if correct_answer else []))),
        "explanation": _clean(question.get("explanation") or ""),
        "difficulty": str(question.get("difficulty") or "medium").lower(),
        "topic": _clean(question.get("topic") or "Study Topic"),
        "concept_id": _clean(question.get("concept_id") or question.get("concept") or ""),
        "expected_keywords": list(dict.fromkeys([_clean(item) for item in question.get("expected_keywords") or [] if _clean(item)]))[:6],
        "quality_score": rank_question_quality(question),
    }


def _normalize_for_match(value: Any) -> str:
    """Normalize punctuation and case for option identity/answer matching."""
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).strip()


def _valid_mcq(question: dict[str, Any], source_text: str = "", requested_topic: str = "") -> bool:
    if str(question.get("type") or "").lower().replace("-", "_").replace(" ", "_") != "mcq":
        return False
    stem = _clean(question.get("question"))
    raw_options = [_clean(option) for option in question.get("options") or [] if _clean(option)]
    normalized_options = [_normalize_for_match(option) for option in raw_options]
    options = list(dict.fromkeys(normalized_options))
    answer = _clean(question.get("correct_answer") or question.get("answer"))
    normalized_answer = _normalize_for_match(answer)
    explanation = _clean(question.get("explanation"))
    if not (len(stem.split()) >= 6 and stem.endswith("?") and len(options) == 4 and normalized_answer in options and explanation):
        return False

    # Ground the answer/explanation in the retrieved evidence, not just the prompt.
    if source_text.strip():
        source_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", source_text.lower()))
        answer_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", answer.lower()))
        explanation_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", explanation.lower()))
        stop = {"the", "and", "for", "with", "that", "this", "from", "into", "which", "when", "where", "what", "how", "why", "are", "was", "were", "has", "have", "can", "will", "does", "using", "used"}
        answer_terms -= stop
        explanation_terms -= stop
        if not answer_terms or len(answer_terms & source_terms) / len(answer_terms) < 0.35:
            return False
        if explanation_terms and len(explanation_terms & source_terms) / len(explanation_terms) < 0.2:
            return False

    if requested_topic:
        topic_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", requested_topic.lower()))
        stem_terms = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", stem.lower()))
        if topic_terms and not (topic_terms & stem_terms or topic_terms & set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", (answer + " " + explanation).lower()))):
            return False
    return True


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
    # The caller may already request extra questions for filtering. Avoid
    # multiplying that pool again and overwhelming providers' token-per-minute limits.
    candidate_limit = min(60, max(limit + 8, int(limit * 1.5)))
    source_text = str(package.get("retrieved_source_text") or "")
    requested_topic = str(package.get("quiz_topic") or "")

    candidates: list[dict[str, Any]] = []
    if has_llm_support():
        try:
            candidates = _llm_candidates(package, candidate_limit)
        except Exception:
            candidates = []
    candidates = [
        question for question in candidates
        if isinstance(question, dict) and _valid_mcq(question, source_text, requested_topic)
    ]

    # Invalid structured output is not an exception; still try the strict
    # source-note fallback when no candidate survives validation.
    if not candidates:
        fallback = _fallback_candidates(package, candidate_limit)
        candidates = [
            question for question in fallback
            if isinstance(question, dict) and _valid_mcq(question, source_text, requested_topic)
        ]
    selected = _select_diverse(candidates, limit, memory=memory)
    random.shuffle(selected)
    return selected
