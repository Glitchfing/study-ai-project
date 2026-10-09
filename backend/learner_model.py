"""Recency-weighted mastery calculations based on persisted quiz attempts.

Scores are represented internally as fractions in [0, 1]. The dashboard
converts them to percentages for display. Attempts must be ordered oldest to
newest before applying the recency weights.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

DEFAULT_DECAY = 0.85
GENERIC_TOPICS = {"", "all", "generated", "mixed", "quiz", "general", "unknown"}


def _parse_timestamp(value: Any) -> datetime:
    """Parse ISO timestamps consistently; missing/invalid values sort first."""
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
    """Convert repository score fields (percentage or ratio) to [0, 1]."""
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
    """Return the exact recency-weighted mastery formula (oldest score first)."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")
    values = list(scores)
    if not values:
        return None
    if any(not isinstance(score, (int, float)) or not 0 <= score <= 1 for score in values):
        raise ValueError("scores must be fractions between 0 and 1.")
    weights = [decay ** (len(values) - index - 1) for index in range(len(values))]
    return sum(score * weight for score, weight in zip(values, weights)) / sum(weights)


def _response_topics(attempt: dict[str, Any]) -> list[tuple[str, float]]:
    """Extract per-topic scores when responses carry topic and correctness data."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for response in attempt.get("responses") or []:
        if not isinstance(response, dict):
            continue
        raw_topic = response.get("topic") or response.get("section_title")
        if not isinstance(raw_topic, str) or raw_topic.strip().lower() in GENERIC_TOPICS:
            continue
        if not isinstance(response.get("is_correct"), bool):
            continue
        topic = " ".join(raw_topic.strip().split())
        totals[topic][1] += 1
        totals[topic][0] += int(response["is_correct"])
    return [
        (topic, correct / total)
        for topic, (correct, total) in totals.items()
        if total > 0
    ]


def _attempt_topic_scores(attempt: dict[str, Any]) -> list[tuple[str, float]]:
    """Prefer response-level topic correctness; otherwise use attempt-level score."""
    response_scores = _response_topics(attempt)
    if response_scores:
        return response_scores

    raw_topic = attempt.get("topic_label") or attempt.get("topic")
    if not isinstance(raw_topic, str):
        return []
    topic = " ".join(raw_topic.strip().split())
    if topic.lower() in GENERIC_TOPICS:
        # Do not accidentally classify every uploaded-note quiz as one topic.
        return []

    # The topic label often contains presentation labels like "Generated Quiz".
    # Keep the stored label when it is a real topic rather than guessing.
    score = _score_fraction(attempt.get("score"))
    if score is None:
        correct = attempt.get("correct")
        total = attempt.get("total")
        if (
            isinstance(correct, (int, float)) and isinstance(total, (int, float))
            and total > 0 and 0 <= correct <= total
        ):
            score = float(correct) / float(total)
    return [(topic, score)] if score is not None else []


def build_topic_mastery(
    attempts: Iterable[dict[str, Any]],
    decay: float = DEFAULT_DECAY,
) -> dict[str, dict[str, Any]]:
    """Build per-topic mastery from persisted attempts in chronological order."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in the interval (0, 1].")

    ordered = sorted(
        (attempt for attempt in attempts if isinstance(attempt, dict)),
        key=lambda item: _parse_timestamp(item.get("created_at")),
    )
    observations: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    last_review: dict[str, datetime] = {}

    for attempt in ordered:
        timestamp = _parse_timestamp(attempt.get("created_at"))
        for topic, score in _attempt_topic_scores(attempt):
            if timestamp == datetime.min.replace(tzinfo=timezone.utc):
                # Keep malformed/missing timestamps deterministic and oldest.
                timestamp = datetime.min.replace(tzinfo=timezone.utc)
            observations[topic].append((timestamp, score))
            last_review[topic] = timestamp

    result: dict[str, dict[str, Any]] = {}
    for topic, events in observations.items():
        scores = [score for _, score in events]
        mastery = calculate_mastery(scores, decay=decay)
        previous = calculate_mastery(scores[:-1], decay=decay) if len(scores) > 1 else None
        latest_score = scores[-1]
        trend = (latest_score - previous) if previous is not None else 0.0
        latest_review = last_review[topic]
        reviewed_at = None if latest_review.year == 1 else latest_review.isoformat(timespec="seconds")
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
