"""Learner state derived only from saved quiz attempts.

Topic and concept mastery are recency-weighted estimates. Concept-level claims
are emitted only when response data explicitly identifies the concept.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from recommendation_config import DEFAULT_DECAY, MIN_ATTEMPTS_FOR_TREND
except ImportError:
    DEFAULT_DECAY = 0.85
    MIN_ATTEMPTS_FOR_TREND = 2

GENERIC_TOPICS = {
    "", "all", "generated", "generated quiz", "generated notes",
    "mixed", "mixed quiz", "quiz", "general", "unknown",
}
MISSING_TIME = datetime.min.replace(tzinfo=timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _score_fraction(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    return score / 100.0 if 0 <= score <= 100 else None


def calculate_mastery(scores: Iterable[float], decay: float = DEFAULT_DECAY) -> float | None:
    """Calculate weighted mastery from fractions ordered oldest-to-newest."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")
    values = list(scores)
    if not values:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in values):
        raise ValueError("scores must be fractions between 0 and 1.")
    weights = [decay ** (len(values) - index - 1) for index in range(len(values))]
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def _clean_label(value: Any) -> str:
    return " ".join(value.strip().split()) if isinstance(value, str) else ""


def _response_observations(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize response correctness and explicit concept metadata."""
    observations = []
    for response in attempt.get("responses") or []:
        if not isinstance(response, dict) or not isinstance(response.get("is_correct"), bool):
            continue
        topic = _clean_label(response.get("topic") or response.get("section_title"))
        if not topic or topic.lower() in GENERIC_TOPICS:
            continue
        concept = _clean_label(
            response.get("concept_id") or response.get("concept") or
            response.get("concept_tag") or response.get("learning_objective")
        )
        observations.append({
            "topic": topic,
            "concept": concept or None,
            "score": float(response["is_correct"]),
            "difficulty": _clean_label(response.get("difficulty")) or None,
            "question_type": _clean_label(response.get("type")) or None,
            "timestamp": _parse_timestamp(attempt.get("created_at")),
            "attempt_id": attempt.get("id"),
            "note_id": attempt.get("note_id"),
            "note_title": attempt.get("note_title"),
        })
    return observations


def _attempt_topic_scores(attempt: dict[str, Any]) -> list[tuple[str, float]]:
    """Prefer individual response topics; use the attempt score as fallback."""
    observations = _response_observations(attempt)
    if observations:
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for item in observations:
            counts[item["topic"]][1] += 1
            counts[item["topic"]][0] += int(item["score"])
        return [(topic, correct / total) for topic, (correct, total) in counts.items() if total]

    raw_topic = _clean_label(attempt.get("topic"))
    if raw_topic.lower() in GENERIC_TOPICS:
        raw_topic = _clean_label(attempt.get("topic_label") or attempt.get("note_title"))
    if not raw_topic or raw_topic.lower() in GENERIC_TOPICS:
        return []
    score = _score_fraction(attempt.get("score"))
    if score is None:
        correct, total = attempt.get("correct"), attempt.get("total")
        if (
            isinstance(correct, (int, float)) and not isinstance(correct, bool)
            and isinstance(total, (int, float)) and not isinstance(total, bool)
            and total > 0 and 0 <= correct <= total
        ):
            score = float(correct) / float(total)
    return [(raw_topic, score)] if score is not None else []


def _trend(scores: list[float]) -> tuple[float | None, str]:
    if len(scores) < MIN_ATTEMPTS_FOR_TREND:
        return None, "insufficient_data"
    previous = calculate_mastery(scores[:-1])
    if previous is None:
        return None, "insufficient_data"
    delta = scores[-1] - previous
    label = "improving" if delta > 0.03 else "declining" if delta < -0.03 else "stable"
    return round(delta, 4), label


def _summary(
    name: str,
    scores: list[float],
    timestamps: list[datetime | None],
    decay: float,
    *,
    evidence_level: str,
) -> dict[str, Any]:
    mastery = calculate_mastery(scores, decay)
    trend, trend_label = _trend(scores)
    valid_times = [stamp for stamp in timestamps if stamp is not None]
    return {
        "topic" if evidence_level == "topic" else "concept": name,
        "mastery": round(mastery, 4) if mastery is not None else None,
        "mastery_pct": round(mastery * 100, 1) if mastery is not None else None,
        "attempts": len(scores),
        "question_count": None,
        "latest_score": round(scores[-1], 4) if scores else None,
        "trend": trend,
        "trend_label": trend_label,
        "last_reviewed_at": max(valid_times).isoformat(timespec="seconds") if valid_times else None,
        "evidence_confidence": round(min(1.0, len(scores) / 5.0), 2),
        "evidence_level": evidence_level,
        "decay": decay,
    }


def build_topic_mastery(
    attempts: Iterable[dict[str, Any]],
    decay: float = DEFAULT_DECAY,
) -> dict[str, dict[str, Any]]:
    """Build per-topic summaries from stored quiz attempts."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")
    ordered = sorted(
        (item for item in attempts if isinstance(item, dict)),
        key=lambda item: _parse_timestamp(item.get("created_at")) or MISSING_TIME,
    )
    observations: dict[str, list[tuple[datetime | None, float]]] = defaultdict(list)
    metadata: dict[str, dict[str, Any]] = {}
    for attempt in ordered:
        timestamp = _parse_timestamp(attempt.get("created_at"))
        for topic, score in _attempt_topic_scores(attempt):
            observations[topic].append((timestamp, score))
            metadata[topic] = {
                "note_id": attempt.get("note_id"),
                "note_title": attempt.get("note_title") or attempt.get("topic_label"),
                "latest_attempt_id": attempt.get("id"),
            }

    result: dict[str, dict[str, Any]] = {}
    for topic, events in observations.items():
        scores = [score for _, score in events]
        row = _summary(topic, scores, [stamp for stamp, _ in events], decay, evidence_level="topic")
        row["attempts"] = len(events)
        response_count = sum(
            1 for attempt in ordered
            for response in _response_observations(attempt)
            if response["topic"] == topic
        )
        row["question_count"] = response_count or None
        row.update(metadata.get(topic, {}))
        result[topic] = row
    return result


def build_concept_mastery(
    attempts: Iterable[dict[str, Any]],
    decay: float = DEFAULT_DECAY,
) -> dict[str, dict[str, Any]]:
    """Build concept summaries only where saved responses have explicit concept tags."""
    ordered = sorted(
        (item for item in attempts if isinstance(item, dict)),
        key=lambda item: _parse_timestamp(item.get("created_at")) or MISSING_TIME,
    )
    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in ordered:
        for row in _response_observations(attempt):
            if row["concept"]:
                observations[row["concept"]].append(row)

    result: dict[str, dict[str, Any]] = {}
    for concept, rows in observations.items():
        scores = [row["score"] for row in rows]
        summary = _summary(concept, scores, [row["timestamp"] for row in rows], decay, evidence_level="concept")
        observed_attempt_ids = {
            str(row["attempt_id"]) for row in rows if row.get("attempt_id")
        }
        observed_timestamps = {
            row["timestamp"].isoformat(timespec="seconds")
            for row in rows if row.get("timestamp") is not None and not row.get("attempt_id")
        }
        distinct_attempts = len(observed_attempt_ids | observed_timestamps)
        summary.update({
            "concept": concept,
            "topic": rows[-1]["topic"],
            "attempts": distinct_attempts,
            "evidence_confidence": round(min(1.0, distinct_attempts / 5.0), 2),
            "question_count": len(rows),
            "incorrect_count": sum(score == 0 for score in scores),
            "question_types": sorted({row["question_type"] for row in rows if row["question_type"]}),
            "difficulties": sorted({row["difficulty"] for row in rows if row["difficulty"]}),
            "note_id": next((row["note_id"] for row in reversed(rows) if row["note_id"]), None),
            "note_title": next((row["note_title"] for row in reversed(rows) if row["note_title"]), None),
        })
        result[concept] = summary
    return result
