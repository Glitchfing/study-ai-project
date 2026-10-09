"""Recency-weighted mastery calculations based on persisted quiz attempts.

Scores are represented internally as fractions in [0, 1]. Attempts are sorted
oldest-to-newest before applying the recency weights from the research model.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

DEFAULT_DECAY = 0.85
GENERIC_TOPICS = {
    "", "all", "generated", "generated quiz", "generated notes",
    "mixed", "mixed quiz", "quiz", "general", "unknown",
}


def _parse_timestamp(value: Any) -> datetime:
    """Parse ISO timestamps consistently; invalid timestamps sort first."""
    if not isinstance(value, str) or not value.strip():
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _score_fraction(value: Any) -> float | None:
    """Convert a percentage (0-100) or fraction (0-1) into [0, 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if score < 0:
        return None
    if score > 1:
        score /= 100.0
    if score > 1:
        return None
    return score


def calculate_mastery(scores: Iterable[float], decay: float = DEFAULT_DECAY) -> float | None:
    """Calculate P_t; scores must be fractions ordered oldest to newest."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")
    values = list(scores)
    if not values:
        return None
    if any(
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 1
        for score in values
    ):
        raise ValueError("scores must be fractions between 0 and 1.")
    weights = [
        decay ** (len(values) - index - 1)
        for index in range(len(values))
    ]
    return sum(score * weight for score, weight in zip(values, weights)) / sum(weights)


def _response_topic_scores(attempt: dict[str, Any]) -> list[tuple[str, float]]:
    """Aggregate per-question correctness into one score per topic per attempt."""
    topic_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for response in attempt.get("responses") or []:
        if not isinstance(response, dict):
            continue
        raw_topic = response.get("topic") or response.get("section_title")
        if not isinstance(raw_topic, str):
            continue
        topic = " ".join(raw_topic.strip().split())
        if topic.lower() in GENERIC_TOPICS or not isinstance(response.get("is_correct"), bool):
            continue
        topic_counts[topic][1] += 1
        topic_counts[topic][0] += int(response["is_correct"])
    return [
        (topic, correct / total)
        for topic, (correct, total) in topic_counts.items()
        if total
    ]


def _attempt_topic_scores(attempt: dict[str, Any]) -> list[tuple[str, float]]:
    """Prefer response-level topics; fall back to the attempt's named topic."""
    per_topic = _response_topic_scores(attempt)
    if per_topic:
        return per_topic

    raw_topic = attempt.get("topic")
    label = attempt.get("topic_label") or attempt.get("note_title")
    if not isinstance(raw_topic, str):
        raw_topic = ""
    if raw_topic.strip().lower() in GENERIC_TOPICS:
        raw_topic = label if isinstance(label, str) else ""
    topic = " ".join(raw_topic.strip().split())
    if not topic or topic.lower() in GENERIC_TOPICS:
        return []

    score = _score_fraction(attempt.get("score"))
    if score is None:
        correct = attempt.get("correct")
        total = attempt.get("total")
        if (
            isinstance(correct, (int, float))
            and isinstance(total, (int, float))
            and total > 0 and 0 <= correct <= total
        ):
            score = float(correct) / float(total)
    return [(topic, score)] if score is not None else []


def build_topic_mastery(
    attempts: Iterable[dict[str, Any]],
    decay: float = DEFAULT_DECAY,
) -> dict[str, dict[str, Any]]:
    """Build per-topic mastery summaries from stored quiz attempts."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")

    ordered = sorted(
        (attempt for attempt in attempts if isinstance(attempt, dict)),
        key=lambda item: _parse_timestamp(item.get("created_at")),
    )
    observations: dict[str, list[tuple[datetime, float]]] = defaultdict(list)

    for attempt in ordered:
        timestamp = _parse_timestamp(attempt.get("created_at"))
        for topic, score in _attempt_topic_scores(attempt):
            observations[topic].append((timestamp, score))

    result: dict[str, dict[str, Any]] = {}
    missing_timestamp = datetime.min.replace(tzinfo=timezone.utc)
    for topic, events in observations.items():
        scores = [score for _, score in events]
        mastery = calculate_mastery(scores, decay=decay)
        previous_mastery = calculate_mastery(scores[:-1], decay=decay) if len(scores) > 1 else None
        latest_score = scores[-1]
        trend = latest_score - previous_mastery if previous_mastery is not None else 0.0
        last_review = events[-1][0]
        reviewed_at = None if last_review == missing_timestamp else last_review.isoformat(timespec="seconds")
        result[topic] = {
            "topic": topic,
            "mastery": round(mastery, 4) if mastery is not None else None,
            "mastery_pct": round(mastery * 100, 1) if mastery is not None else None,
            "attempts": len(scores),
            "latest_score": round(latest_score, 4),
            "trend": round(trend, 4),
            "last_reviewed_at": reviewed_at,
            "decay": decay,
        }
    return result
