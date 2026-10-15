"""Transparent, configurable baseline for learner recommendations.

These heuristic weights are an initial baseline, not empirically validated model
parameters. Keep weights here so they can be tuned and evaluated without editing
recommendation generation logic.
"""
from __future__ import annotations

DEFAULT_WEIGHTS = {
    "weakness": 0.35,
    "decline": 0.20,
    "review_need": 0.20,
    "learning_importance": 0.15,
    "uncertainty": 0.10,
}

DEFAULT_DECAY = 0.85
DEFAULT_RECOMMENDATION_LIMIT = 3
MIN_ATTEMPTS_FOR_TREND = 2
LOW_MASTERY_THRESHOLD = 0.45
PARTIAL_MASTERY_THRESHOLD = 0.65
STRONG_MASTERY_THRESHOLD = 0.82
ACTIVE_RECOMMENDATION_STATUSES = {"pending", "in_progress"}
VALID_RECOMMENDATION_STATUSES = {
    "pending", "in_progress", "completed", "dismissed", "reevaluated"
}
