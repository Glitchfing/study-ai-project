"""Transparent personalized recommendation ranking.

Scores are deterministic, explainable heuristics. They are not a learned or
experimentally validated model. Recommendations are based only on saved learner
evidence; missing timestamps are unknown rather than overdue.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

try:
    from recommendation_config import (
        DEFAULT_RECOMMENDATION_LIMIT, DEFAULT_WEIGHTS,
        LOW_MASTERY_THRESHOLD, PARTIAL_MASTERY_THRESHOLD, STRONG_MASTERY_THRESHOLD,
    )
except ImportError:
    DEFAULT_WEIGHTS = {
        "weakness": 0.35, "decline": 0.20, "review_need": 0.20,
        "learning_importance": 0.15, "uncertainty": 0.10,
    }
    DEFAULT_RECOMMENDATION_LIMIT = 3
    LOW_MASTERY_THRESHOLD = 0.45
    PARTIAL_MASTERY_THRESHOLD = 0.65
    STRONG_MASTERY_THRESHOLD = 0.82


def _days_since(timestamp: str | None, now: datetime) -> float | None:
    """Return elapsed days only for a valid saved timestamp."""
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    try:
        reviewed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
        elapsed = (now - reviewed_at.astimezone(timezone.utc)).total_seconds() / 86400
        return max(0.0, elapsed)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _action_for(mastery: float, trend: float | None, *, diagnostic: bool = False) -> str:
    """Select an action appropriate to mastery and evidence strength."""
    if diagnostic:
        return "Practice Quiz"
    if mastery < LOW_MASTERY_THRESHOLD:
        return "Deep Study" if not (trend is not None and trend < -0.05) else "Revise Topic"
    if mastery < PARTIAL_MASTERY_THRESHOLD:
        return "Revise Topic"
    if mastery < STRONG_MASTERY_THRESHOLD:
        return "Practice Quiz"
    return "Reassessment"


def _action_utilities(mastery: float, trend: float | None) -> dict[str, float]:
    """Rules choose an action; this mapping is retained for explainability."""
    if mastery < LOW_MASTERY_THRESHOLD:
        values = {"Deep Study": 1.0, "Revise Topic": 0.95, "Practice Quiz": 0.7, "Reassessment": 0.2}
    elif mastery < PARTIAL_MASTERY_THRESHOLD:
        values = {"Revise Topic": 1.0, "Deep Study": 0.8, "Practice Quiz": 0.75, "Reassessment": 0.35}
    elif mastery < STRONG_MASTERY_THRESHOLD:
        values = {"Practice Quiz": 1.0, "Reassessment": 0.85, "Revise Topic": 0.7, "Deep Study": 0.4}
    else:
        values = {"Reassessment": 1.0, "Practice Quiz": 0.85, "Revise Topic": 0.5, "Deep Study": 0.25}
    if trend is not None and trend < -0.05:
        values["Revise Topic"] = min(1.0, values["Revise Topic"] + 0.08)
        values["Deep Study"] = min(1.0, values["Deep Study"] + 0.08)
    if trend is not None and trend > 0.08:
        values["Reassessment"] = min(1.0, values["Reassessment"] + 0.08)
    return values


def _stable_id(topic: str, concept: str | None, action: str) -> str:
    key = "|".join([_normalize(topic), _normalize(concept), _normalize(action)])
    return "rec-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _reason(topic: str, concept: str | None, mastery_pct: float, trend: float | None,
            attempts: int | None, question_count: int | None, elapsed: float | None,
            diagnostic: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if diagnostic:
        reasons.append("There is not enough quiz history to estimate mastery confidently")
    elif mastery_pct < 45:
        reasons.append(f"low estimated mastery ({round(mastery_pct)}%)")
    elif mastery_pct < 65:
        reasons.append(f"partial estimated mastery ({round(mastery_pct)}%)")
    if trend is not None and trend < -0.05:
        reasons.append("recent performance is declining")
    elif trend is not None and trend > 0.05:
        reasons.append("recent performance is improving; a follow-up check can verify retention")
    if question_count is not None and question_count > 0:
        reasons.append(f"based on {question_count} saved question response(s)")
    if attempts is not None:
        reasons.append(f"{attempts} saved quiz attempt(s)")
    if elapsed is not None and elapsed >= 3:
        reasons.append(f"last reviewed {round(elapsed)} day(s) ago")
    if not reasons:
        reasons.append("a short check can help maintain retention")
    target = f"{topic} — {concept}" if concept else topic
    return f"{target}: " + "; ".join(reasons) + ".", reasons


def build_recommendations(
    topic_mastery: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
    concept_mastery: dict[str, dict[str, Any]] | None = None,
    revision_tasks: list[dict[str, Any]] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Rank evidence-backed learning actions; one active candidate per topic."""
    chosen_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    if set(chosen_weights) != set(DEFAULT_WEIGHTS):
        raise ValueError(f"Weights must define exactly: {', '.join(DEFAULT_WEIGHTS)}")
    if any(not isinstance(value, (int, float)) or value < 0 for value in chosen_weights.values()):
        raise ValueError("Recommendation weights must be non-negative numbers.")
    if abs(sum(chosen_weights.values()) - 1.0) > 1e-9:
        raise ValueError("Recommendation weights must sum to 1.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    max_items = DEFAULT_RECOMMENDATION_LIMIT if limit is None else max(0, int(limit))

    concepts_by_topic: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for concept, stats in (concept_mastery or {}).items():
        topic = str(stats.get("topic") or "").strip()
        if topic and isinstance(stats.get("mastery_pct"), (int, float)):
            concepts_by_topic.setdefault(_normalize(topic), []).append((concept, stats))

    candidates: list[dict[str, Any]] = []
    for topic, stats in topic_mastery.items():
        topic_pct = stats.get("mastery_pct")
        if not isinstance(topic_pct, (int, float)):
            continue
        topic_elapsed = _days_since(stats.get("last_reviewed_at"), current_time)
        topic_trend_value = stats.get("trend")
        topic_trend = float(topic_trend_value) if isinstance(topic_trend_value, (int, float)) else None

        eligible_concepts = [
            item for item in concepts_by_topic.get(_normalize(topic), [])
            if int(item[1].get("attempts") or 0) >= 2
            and int(item[1].get("question_count") or 0) >= 2
            and (float(item[1].get("mastery_pct") or 0) < 70
                 or (isinstance(item[1].get("trend"), (int, float)) and item[1]["trend"] < -0.05))
        ]
        selected_concept = min(
            eligible_concepts,
            key=lambda item: (float(item[1].get("mastery_pct") or 0),
                              -int(item[1].get("incorrect_count") or 0), str(item[0]).lower()),
            default=None,
        )
        concept = selected_concept[0] if selected_concept else None
        focus_stats = selected_concept[1] if selected_concept else stats
        focus_pct = min(100.0, max(0.0, float(focus_stats.get("mastery_pct", topic_pct))))
        focus_mastery = focus_pct / 100.0

        # Report the number of attempts supporting the actual focus. For a
        # concept recommendation this is concept evidence, not the topic total.
        raw_attempts = focus_stats.get("attempts", stats.get("attempts"))
        attempt_count = int(raw_attempts) if isinstance(raw_attempts, (int, float)) and raw_attempts >= 0 else None
        raw_questions = focus_stats.get("question_count")
        question_count = int(raw_questions) if isinstance(raw_questions, (int, float)) and raw_questions >= 0 else None
        confidence_value = focus_stats.get("evidence_confidence", stats.get("evidence_confidence"))
        if isinstance(confidence_value, (int, float)):
            confidence = min(1.0, max(0.0, float(confidence_value)))
        elif attempt_count is not None:
            confidence = min(1.0, attempt_count / 5.0)
        else:
            confidence = None
        diagnostic = (attempt_count is None or attempt_count < 2) and not selected_concept

        raw_trend = focus_stats.get("trend")
        trend = float(raw_trend) if isinstance(raw_trend, (int, float)) else topic_trend
        elapsed = _days_since(focus_stats.get("last_reviewed_at"), current_time)
        if elapsed is None:
            elapsed = topic_elapsed

        # A missing signal is excluded and the available weights are
        # renormalized. Unknown trend/review dates must not be scored as
        # observed stability or urgency.
        review_need = min(1.0, elapsed / 7.0) if elapsed is not None else None
        components: dict[str, float | None] = {
            "weakness": 1.0 - focus_mastery,
            "decline": min(1.0, max(0.0, -trend / 0.25)) if trend is not None else None,
            "review_need": review_need,
            "learning_importance": (
                min(1.0, max(0.0, float(importance_value)))
                if isinstance((importance_value := focus_stats.get("learning_importance", stats.get("learning_importance"))), (int, float))
                else None
            ),
            "uncertainty": 1.0 - confidence if confidence is not None else None,
        }
        available_weight = sum(chosen_weights[key] for key, value in components.items() if value is not None)
        priority = (
            sum(chosen_weights[key] * float(value) for key, value in components.items() if value is not None)
            / available_weight
            if available_weight > 0 else 0.0
        )
        priority_components = {
            key: {
                "value": round(float(value), 4),
                "configured_weight": chosen_weights[key],
                "effective_weight": round(chosen_weights[key] / available_weight, 4),
            }
            for key, value in components.items() if value is not None
        }

        action = _action_for(focus_mastery, trend, diagnostic=diagnostic)
        utilities = _action_utilities(focus_mastery, trend)
        display_action = "Diagnostic Practice Quiz" if diagnostic else action
        reason, reason_parts = _reason(topic, concept, focus_pct, trend, attempt_count,
                                       question_count, elapsed, diagnostic)
        next_review_days = (1 if diagnostic or focus_pct < 50 or (trend is not None and trend < -0.15)
                            else 3 if focus_pct < 80 or review_need >= 0.75 else 7)

        candidates.append({
            "id": _stable_id(topic, concept, action),
            "topic": topic,
            "concept": concept,
            "type": "diagnostic" if diagnostic else action.lower().replace(" ", "_"),
            "action": action,
            "title": f"{display_action}: {concept or topic}",
            "mastery_pct": round(focus_pct, 1),
            "topic_mastery_pct": round(float(topic_pct), 1),
            "trend": round(trend, 4) if trend is not None else None,
            "trend_label": focus_stats.get("trend_label", stats.get("trend_label", "insufficient_data")),
            "attempts": attempt_count,
            "question_count": question_count,
            "evidence_confidence": round(confidence, 2) if confidence is not None else None,
            "evidence_level": "concept" if concept else "topic",
            "evidence": {
                "attempt_count": attempt_count, "question_count": question_count,
                "mastery_pct": round(focus_pct, 1),
                "trend": round(trend, 4) if trend is not None else None,
                "last_reviewed_at": focus_stats.get("last_reviewed_at") or stats.get("last_reviewed_at"),
                "incorrect_count": focus_stats.get("incorrect_count"),
                "question_types": focus_stats.get("question_types") or [],
                "confidence": round(confidence, 2) if confidence is not None else None,
            },
            "priority_components": priority_components,
            "priority_score": round(priority, 4),
            "priority": round(priority, 4),
            "reason": reason,
            "reason_factors": reason_parts,
            "next_review_days": next_review_days,
            "action_payload": {
                "type": action.lower().replace(" ", "_"), "topic": topic, "concept": concept,
                "note_id": focus_stats.get("note_id") or stats.get("note_id"),
                "note_title": focus_stats.get("note_title") or stats.get("note_title"),
                "question_count": 5,
            },
            "status": "pending",
            "created_at": current_time.isoformat(timespec="seconds"),
            "model_version": "1.0",
            "action_utility": round(utilities.get(action, 0.0), 3),
        })

    for task in revision_tasks or []:
        if not isinstance(task, dict) or task.get("id") is None or task.get("done"):
            continue
        task_id = str(task.get("id"))
        topic = str(task.get("topic") or "General")
        candidates.append({
            "id": "planner-" + task_id, "topic": topic, "concept": None,
            "type": "revision_due", "action": "Revise Topic",
            "title": str(task.get("title") or "Complete revision task"),
            "mastery_pct": None, "trend": None, "attempts": None,
            "question_count": None, "evidence_confidence": 1.0, "evidence_level": "planner",
            "evidence": {"planner_task_id": task_id, "planner_status": "pending"},
            "priority_score": 0.0, "priority": 0.0,
            "reason": "This is an unfinished task from your saved revision planner.",
            "reason_factors": ["unfinished saved planner task"], "next_review_days": None,
            "action_payload": {"type": "open_planner_task", "task_id": task.get("id"), "topic": topic},
            "status": "pending", "created_at": current_time.isoformat(timespec="seconds"),
            "model_version": "1.0",
        })

    unique: dict[str, dict[str, Any]] = {}
    for item in candidates:
        key = str(item["id"])
        if key not in unique or item["priority_score"] > unique[key]["priority_score"]:
            unique[key] = item
    ordered = sorted(unique.values(), key=lambda item: (
        item["type"] == "revision_due", -float(item["priority_score"]),
        str(item.get("topic") or "").lower(), str(item.get("concept") or "").lower()
    ))
    return ordered[:max_items]
