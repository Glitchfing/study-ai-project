"""Centralized, adjustable defaults for the StudyAI revision scheduler."""
PRIORITY_WEIGHTS = {
    "weakness": 0.35,
    "decline": 0.20,
    "urgency": 0.20,
    "importance": 0.15,
    "uncertainty": 0.10,
}
MASTERY_THRESHOLDS = {"critical": 0.40, "needs_practice": 0.70, "strong": 0.85}
DEFAULT_DAILY_MINUTES = 60
DEFAULT_PLANNING_DAYS = 7
DEFAULT_START_HOUR = 18
DEFAULT_END_HOUR = 22
DEFAULT_DURATIONS = {
    "quick_review": 15,
    "targeted_practice": 20,
    "deep_revision": 30,
    "assessment": 15,
}
