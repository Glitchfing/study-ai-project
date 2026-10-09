"""Rule-based recommendation scoring aligned to the learner-model equations.

The parameters are transparent starter heuristics and should be calibrated with
the evaluation data before being reported as validated results.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DEFAULT_WEIGHTS = {"weakness": 0.45, "decline": 0.20, "urgency": 0.20, "utility": 0.15}


def _days_since(timestamp: str | None, now: datetime) -> float | None:
    if not timestamp:
        return None
    try:
        reviewed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None:
            reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now - reviewed_at.astimezone(timezone.utc)).total_seconds() / 86400)
    except (TypeError, ValueError, OverflowError):
        return None


def _action_utilities(mastery: float, trend: float) -> dict[str, float]:
    """Contextual U_r values: the most useful action depends on current mastery."""
    if mastery < 0.45:
        utilities = {
            "Deep Study": 1.00,
            "Revise Topic": 0.98,
            "Practice Quiz": 0.55,
            "Reassessment": 0.35,
        }
    elif mastery < 0.65:
        utilities = {
            "Revise Topic": 1.00,
            "Deep Study": 0.85,
            "Practice Quiz": 0.75,
            "Reassessment": 0.50,
        }
    elif mastery < 0.82:
        utilities = {
            "Practice Quiz": 1.00,
            "Revise Topic": 0.75,
            "Reassessment": 0.80,
            "Deep Study": 0.55,
        }
    else:
        utilities = {
            "Reassessment": 1.00,
            "Practice Quiz": 0.85,
            "Revise Topic": 0.55,
            "Deep Study": 0.35,
        }

    # A declining trend makes revision or deep study more useful.
    if trend < -0.05:
        utilities["Revise Topic"] = min(1.0, utilities["Revise Topic"] + 0.10)
        utilities["Deep Study"] = min(1.0, utilities["Deep Study"] + 0.10)
    # Improvement makes reassessment useful for checking retention.
    if trend > 0.08:
        utilities["Reassessment"] = min(1.0, utilities["Reassessment"] + 0.10)
    return utilities


def build_recommendations(
    topic_mastery: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return one highest-scoring learning action for each topic."""
    chosen_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    if any(value < 0 for value in chosen_weights.values()):
        raise ValueError("Recommendation weights cannot be negative.")
    if abs(sum(chosen_weights.values()) - 1.0) > 1e-9:
        raise ValueError("Recommendation weights must sum to 1.")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    recommendations = []
    for topic, stats in topic_mastery.items():
        mastery_pct = stats.get("mastery_pct")
        if not isinstance(mastery_pct, (int, float)):
            continue
        mastery = min(1.0, max(0.0, float(mastery_pct) / 100.0))
        trend = float(stats.get("trend") or 0.0)
        weakness = 1.0 - mastery
        decline = min(1.0, max(0.0, -trend))
        elapsed = _days_since(stats.get("last_reviewed_at"), current_time)
        urgency = 1.0 if elapsed is None else min(1.0, elapsed / 7.0)
        utilities = _action_utilities(mastery, trend)

        action_scores = {
            action: (
                chosen_weights["weakness"] * weakness
                + chosen_weights["decline"] * decline
                + chosen_weights["urgency"] * urgency
                + chosen_weights["utility"] * utility
            )
            for action, utility in utilities.items()
        }
        action = max(action_scores, key=action_scores.get)
        priority = action_scores[action]

        reasons = []
        if mastery < 0.60:
            reasons.append(f"low recency-weighted mastery ({round(mastery * 100)}%)")
        if trend < -0.05:
            reasons.append("recent performance is declining")
        if elapsed is None:
            reasons.append("no reliable review timestamp is available")
        elif elapsed >= 3:
            reasons.append(f"last reviewed {round(elapsed)} day(s) ago")
        if not reasons:
            reasons.append("use a short practice check to maintain retention")

        next_review_days = 1 if mastery < 0.50 or trend < -0.15 else 3 if mastery < 0.80 or urgency >= 0.75 else 7
        recommendations.append({
            "topic": topic,
            "mastery_pct": round(mastery * 100, 1),
            "trend": round(trend, 4),
            "urgency": round(urgency, 4),
            "action": action,
            "priority": round(priority, 4),
            "reason": f"{topic}: " + "; ".join(reasons) + ".",
            "next_review_days": next_review_days,
        })

    recommendations.sort(key=lambda item: (-item["priority"], item["topic"].lower()))
    return recommendations
