from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
import re
from typing import Any

from learner_model import build_topic_mastery
from recommendation_service import build_recommendations
from quiz_attempt_store import list_quiz_attempts
from session_store import list_sessions

BASE_USER = {
    "name": "RUTU",
    "initials": "RU",
    "role": "Individual Learning",
    "streak": 0,
}

BASE_KPIS = {
    "mastery": 0,
    "topics_mastered": 0,
    "study_minutes": 0,
    "quizzes_completed": 0,
}

BASE_TOPICS = [
    {
        "id": "nlp",
        "name": "NLP & Text",
        "sub": "No activity yet",
        "pct": 0,
        "color": "teal",
        "orb_colors": [0x119DA4, 0x83C5BE],
    },
    {
        "id": "ml",
        "name": "ML Models",
        "sub": "No activity yet",
        "pct": 0,
        "color": "coral",
        "orb_colors": [0xE29578, 0xC1694F],
    },
    {
        "id": "ds",
        "name": "Data Structures",
        "sub": "No activity yet",
        "pct": 0,
        "color": "aqua",
        "orb_colors": [0x64B6AC, 0xC0FDFB],
    },
]

ACTIVITY_LOG: list[dict[str, Any]] = []
USER_PROFILE = deepcopy(BASE_USER)


def record_activity(kind: str, **payload: Any) -> dict[str, Any]:
    entry = {
        "kind": kind,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    ACTIVITY_LOG.append(entry)
    if len(ACTIVITY_LOG) > 1000:
        del ACTIVITY_LOG[: len(ACTIVITY_LOG) - 1000]
    return entry


def _unique_days() -> list[date]:
    days = set()
    for entry in ACTIVITY_LOG:
        try:
            days.add(datetime.fromisoformat(entry["timestamp"]).date())
        except Exception:
            continue
    return sorted(days)


def _streak_from_days(days: list[date]) -> int:
    if not days:
        return 0

    day_set = set(days)
    streak = 0
    cursor = date.today()
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _normalize_topic_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _topic_summary(topic_mastery: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Render dashboard topics from persisted quiz mastery, never activity counters."""
    aliases = {
        "nlp": {"nlp", "nlp text", "natural language processing"},
        "ml": {"ml", "ml models", "machine learning", "machine learning models"},
        "ds": {"ds", "data structures", "data structure", "dsa"},
    }
    topics: list[dict[str, Any]] = []
    used_topics: set[str] = set()

    for base in BASE_TOPICS:
        base_aliases = aliases.get(base["id"], {_normalize_topic_name(base["name"])})
        found_name = next((name for name in topic_mastery if _normalize_topic_name(name) in base_aliases), None)
        stats = topic_mastery.get(found_name) if found_name else None
        if found_name:
            used_topics.add(found_name)
        pct = int(round(stats["mastery_pct"])) if stats and stats.get("mastery_pct") is not None else 0
        if not stats:
            sub = "No quiz attempts yet"
        else:
            trend = stats.get("trend", 0)
            trend_label = "improving" if trend > 0.03 else "declining" if trend < -0.03 else "stable"
            sub = f"{stats.get('attempts', 0)} quiz attempt(s) · {trend_label}"
        topics.append({**base, "pct": max(0, min(100, pct)), "sub": sub})

    candidates = sorted(
        ((name, stats) for name, stats in topic_mastery.items() if name not in used_topics),
        key=lambda item: (float(item[1].get("mastery_pct") or 0), item[0].lower()),
    )
    for topic_name, stats in candidates:
        if len(topics) >= 6:
            break
        attempts_count = int(stats.get("attempts") or 0)
        trend = stats.get("trend", 0)
        trend_label = "improving" if trend > 0.03 else "declining" if trend < -0.03 else "stable"
        color = ("teal", "coral", "aqua")[len(topics) % 3]
        pct = int(round(stats.get("mastery_pct") or 0))
        slug = re.sub(r"[^a-z0-9]+", "-", topic_name.lower()).strip("-") or f"topic-{len(topics)}"
        orb_colors = [0x119DA4, 0x83C5BE] if color == "teal" else [0xE29578, 0xC1694F] if color == "coral" else [0x64B6AC, 0xC0FDFB]
        topics.append({
            "id": slug,
            "name": topic_name,
            "sub": f"{attempts_count} quiz attempt(s) · {trend_label}",
            "pct": max(0, min(100, pct)),
            "color": color,
            "orb_colors": orb_colors,
        })
    return topics


def _format_minutes(minutes: int) -> dict[str, Any]:
    hours = minutes // 60
    mins = minutes % 60
    return {"value": str(hours), "suffix": f"h {mins:02d}m"}


def _study_minutes_from_activity() -> int:
    study_minutes = BASE_KPIS["study_minutes"]
    for entry in ACTIVITY_LOG:
        kind = entry["kind"]
        if kind == "upload_processed":
            study_minutes += 25
        elif kind == "note_view":
            study_minutes += 8
        elif kind == "quiz_completed":
            study_minutes += 20
        elif kind == "planner_task_done":
            study_minutes += 15
        elif kind == "chat_message":
            study_minutes += 5
    return study_minutes


def _recent_quizzes(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use persistent quiz attempts so recent quizzes survive backend restarts."""
    recent = []
    for attempt in attempts[:3]:  # list_quiz_attempts returns newest first
        try:
            score = int(attempt.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        difficulty = "Easy" if score >= 85 else "Medium" if score >= 65 else "Hard"
        variant = "green" if score >= 85 else "teal" if score >= 65 else "coral"
        performance = attempt.get("performance") or {}
        recent.append({
            "title": attempt.get("topic_label") or attempt.get("note_title") or str(attempt.get("topic") or "Quiz").title(),
            "score": max(0, min(100, score)),
            "difficulty": difficulty,
            "icon": "✓" if score >= 60 else "~",
            "variant": variant,
            "feedback": performance.get("feedback"),
        })
    return recent


def _tips_from_activity(
    attempts: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tips: list[dict[str, Any]] = []
    latest_upload = next(
        (entry for entry in reversed(ACTIVITY_LOG) if entry["kind"] == "upload_processed"),
        None,
    )
    completed_tasks = sum(
        1 for entry in ACTIVITY_LOG
        if entry["kind"] == "planner_task_done" and entry.get("done")
    )

    # Surface calculated recommendations in the existing dashboard AI Tips area.
    for rec in recommendations[:2]:
        tips.append({
            "icon": "🎯",
            "title": f"Recommended: {rec['action']}",
            "body": rec["reason"] + f" Suggested review in {rec['next_review_days']} day(s).",
        })

    if attempts:
        latest_quiz = attempts[0]
        score = int(latest_quiz.get("score") or 0)
        weak_topics = latest_quiz.get("weak_topics") or []
        if len(tips) < 3:
            tips.append({
                "icon": "📝",
                "title": "Latest Quiz Feedback",
                "body": f"Your latest saved quiz score was {score}%. Review missed concepts before moving on.",
            })
        if weak_topics and len(tips) < 3:
            tips.append({
                "icon": "!",
                "title": "Missed Concepts",
                "body": f"Focus next on {', '.join(weak_topics[:3])}. These came from your latest quiz responses.",
            })

    if latest_upload and len(tips) < 3:
        tips.append({
            "icon": "📄",
            "title": "New Upload Detected",
            "body": f"{latest_upload.get('filename', 'Your file')} was processed. Turn it into notes and a quick quiz next.",
        })

    if completed_tasks and len(tips) < 3:
        tips.append({
            "icon": "✅",
            "title": "Planner Momentum",
            "body": f"You completed {completed_tasks} planner task(s). Keep going with a short review block.",
        })

    return tips[:3]


def _activity_heatmap(weeks: int = 18) -> list[list[dict[str, Any]]]:
    counts = Counter()
    for entry in ACTIVITY_LOG:
        try:
            counts[datetime.fromisoformat(entry["timestamp"]).date()] += 1
        except Exception:
            continue

    today = date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    cells: list[list[dict[str, Any]]] = []
    for week in range(weeks):
        col = []
        for day in range(7):
            current = start + timedelta(days=week * 7 + day)
            count = counts.get(current, 0)
            if count <= 0:
                lvl = ""
            elif count == 1:
                lvl = "l1"
            elif count == 2:
                lvl = "l2"
            elif count == 3:
                lvl = "l3"
            else:
                lvl = "l4"

            tip = f"{count} activity" if count == 1 else f"{count} activities"
            if count == 0:
                tip = "No activity"

            col.append({"lvl": lvl, "tip": tip, "date": current.isoformat()})
        cells.append(col)
    return cells


def _add_months(base: date, months: int) -> date:
    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def build_dashboard_payload() -> dict[str, Any]:
    days = _unique_days()
    streak = _streak_from_days(days)
    study_minutes = _study_minutes_from_activity()
    sessions = list_sessions()
    attempts = list_quiz_attempts(limit=1000)
    quiz_completed = len(attempts)
    uploaded_files_count = sum(len(session.get("uploaded_files") or []) for session in sessions)
    diagrams_generated = sum(
        int(file_info.get("diagram_count") or 0)
        for session in sessions
        for file_info in session.get("uploaded_files") or []
    )
    scores = [int(attempt.get("score", 0)) for attempt in attempts]
    highest_score = max(scores) if scores else 0
    average_score = round(sum(scores) / len(scores), 1) if scores else 0
    weak_counter = Counter()
    emoji_history = []
    for attempt in attempts:
        weak_counter.update(attempt.get("weak_topics") or [])
        performance = attempt.get("performance") or {}
        if performance:
            emoji_history.append(
                {
                    "attempt_id": attempt.get("id"),
                    "created_at": attempt.get("created_at"),
                    "score": attempt.get("correct", 0),
                    "total": attempt.get("total", 0),
                    "percentage": attempt.get("score", 0),
                    "emoji": performance.get("emoji"),
                    "feedback": performance.get("feedback"),
                }
            )
    topic_mastery = build_topic_mastery(attempts)
    recommendations = build_recommendations(topic_mastery)
    topic_summary = _topic_summary(topic_mastery)
    mastered_topics = sum(
        1 for stats in topic_mastery.values()
        if (stats.get("mastery_pct") or 0) >= 80
    )
    mastery_values = [
        float(stats["mastery_pct"])
        for stats in topic_mastery.values()
        if stats.get("mastery_pct") is not None
    ]
    mastery = int(round(sum(mastery_values) / len(mastery_values))) if mastery_values else 0

    month_counts = Counter()
    for entry in ACTIVITY_LOG:
        try:
            dt = datetime.fromisoformat(entry["timestamp"])
        except Exception:
            continue
        month_counts[(dt.year, dt.month)] += 1

    today = date.today().replace(day=1)
    months = []
    for offset in range(-11, 1):
        months.append(_add_months(today, offset))

    bar_chart = []
    for month in months:
        activity_boost = month_counts.get((month.year, month.month), 0) * 6
        bar_chart.append({"month": month.strftime("%b"), "value": min(100, activity_boost)})

    recent_quizzes = _recent_quizzes(attempts)
    tips = _tips_from_activity(attempts, recommendations)

    return {
        "user": {**USER_PROFILE, "streak": streak},
        "kpis": [
            {
                "id": "mastery",
                "icon": "🎯",
                "label": "Average Mastery",
                "value": str(mastery),
                "suffix": "%",
                "delta": "Calculated from recency-weighted quiz history" if topic_mastery else "Complete a quiz to build mastery",
                "positive": True,
                "link": "quiz",
            },
            {
                "id": "topics",
                "icon": "📚",
                "label": "Topics Mastered",
                "value": str(mastered_topics),
                "suffix": f"/{len(topic_mastery)}" if topic_mastery else "/6",
                "delta": f"{max(0, len(topic_mastery) - mastered_topics)} topics to strengthen" if topic_mastery else "Start studying to unlock progress",
                "positive": True,
                "link": "notes",
            },
            {
                "id": "time",
                "icon": "⏱",
                "label": "Study Time",
                **_format_minutes(study_minutes),
                "delta": "Tracked from logs" if ACTIVITY_LOG else "No study time yet",
                "positive": True,
                "link": None,
            },
            {
                "id": "quizzes",
                "icon": "✅",
                "label": "Quizzes Completed",
                "value": str(quiz_completed),
                "suffix": "",
                "delta": f"{quiz_completed} saved attempts" if quiz_completed else "No quizzes completed yet",
                "positive": True,
                "link": "quiz",
            },
        ],
        "topics": topic_summary,
        "long_term_stats": {
            "total_activities": f"{len(ACTIVITY_LOG):,}",
            "longest_streak": f"{streak} days",
            "active_days": len(days),
        },
        "bar_chart": bar_chart,
        "recent_quizzes": recent_quizzes,
        "tips": tips,
        "heatmap_weeks": 18,
        "activity_heatmap": _activity_heatmap(18),
        "recent_activity": list(reversed(ACTIVITY_LOG[-8:])),
        "analytics": {
            "total_sessions": len(sessions),
            "uploaded_files_count": uploaded_files_count,
            "quizzes_attempted": len(attempts) or quiz_completed,
            "highest_score": highest_score,
            "average_score": average_score,
            "weak_topics": [{"topic": topic, "count": count} for topic, count in weak_counter.most_common(6)],
            "most_difficult_topics": [{"topic": topic, "count": count} for topic, count in weak_counter.most_common(3)],
            "diagrams_generated": diagrams_generated,
            "learning_progress": mastery,
            "study_minutes": study_minutes,
            "topics_mastered": mastered_topics,
            "emoji_performance_history": emoji_history[:8],
        },
    }
