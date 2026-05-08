from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

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


def _topic_summary() -> list[dict[str, Any]]:
    counts = Counter()
    quiz_scores: dict[str, list[int]] = {}
    for entry in ACTIVITY_LOG:
        topic = entry.get("topic")
        if topic:
            counts[topic] += 1
        if entry["kind"] == "quiz_completed" and topic and isinstance(entry.get("score"), (int, float)):
            quiz_scores.setdefault(topic, []).append(int(entry["score"]))

    topics = []
    known_topic_ids = {base["id"] for base in BASE_TOPICS}
    for base in BASE_TOPICS:
        topic_count = counts.get(base["id"], 0)
        average_score = None
        if quiz_scores.get(base["id"]):
            average_score = sum(quiz_scores[base["id"]]) / len(quiz_scores[base["id"]])

        pct = 0
        if topic_count:
            pct = min(99, topic_count * 12)
        if average_score is not None:
            pct = min(99, max(pct, int(round(average_score))))

        if topic_count:
            sub = f"{topic_count} recent actions"
        else:
            sub = "Start studying to build this topic"

        topics.append({**base, "pct": pct, "sub": sub})

    for topic_id, topic_count in counts.most_common():
        if topic_id in known_topic_ids or not topic_id:
            continue
        scores = quiz_scores.get(topic_id, [])
        average_score = sum(scores) / len(scores) if scores else None
        pct = min(99, topic_count * 10)
        if average_score is not None:
            pct = min(99, max(pct, int(round(average_score))))
        label = "Generated Notes" if topic_id == "generated" else str(topic_id).replace("_", " ").title()
        topics.append(
            {
                "id": topic_id,
                "name": label,
                "sub": f"{topic_count} recent actions",
                "pct": pct,
                "color": "teal" if len(topics) % 3 == 0 else "coral" if len(topics) % 3 == 1 else "aqua",
                "orb_colors": [0x119DA4, 0x83C5BE],
            }
        )
        if len(topics) >= 6:
            break

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


def _recent_quizzes() -> list[dict[str, Any]]:
    quiz_events = [entry for entry in ACTIVITY_LOG if entry["kind"] == "quiz_completed"]
    if not quiz_events:
        return []

    recent = []
    for entry in reversed(quiz_events[-3:]):
        score = int(entry.get("score", 0))
        difficulty = "Easy" if score >= 85 else "Medium" if score >= 65 else "Hard"
        variant = "green" if score >= 85 else "teal" if score >= 65 else "coral"
        recent.append(
            {
                "title": entry.get("topic_label") or entry.get("topic", "Quiz").title(),
                "score": score,
                "difficulty": difficulty,
                "icon": "✓" if score >= 60 else "~",
                "variant": variant,
            }
        )
    return recent


def _tips_from_activity() -> list[dict[str, Any]]:
    tips = []

    latest_upload = next((entry for entry in reversed(ACTIVITY_LOG) if entry["kind"] == "upload_processed"), None)
    latest_quiz = next((entry for entry in reversed(ACTIVITY_LOG) if entry["kind"] == "quiz_completed"), None)
    completed_tasks = sum(1 for entry in ACTIVITY_LOG if entry["kind"] == "planner_task_done" and entry.get("done"))

    if latest_upload:
        tips.append(
            {
                "icon": "📄",
                "title": "New Upload Detected",
                "body": f"{latest_upload.get('filename', 'Your file')} was processed. Turn it into notes and a quick quiz next.",
            }
        )

    if latest_quiz:
        score = int(latest_quiz.get("score", 0))
        weak_topics = latest_quiz.get("weak_topics") or []
        tips.append(
            {
                "icon": "🎯",
                "title": "Quiz Feedback",
                "body": f"Your latest quiz score was {score}%. Review the missed concepts before the next session.",
            }
        )
        if weak_topics:
            tips.append(
                {
                    "icon": "!",
                    "title": "Recommended Revision",
                    "body": f"Focus next on {', '.join(weak_topics[:3])}. These came from your latest quiz responses.",
                }
            )

    if completed_tasks:
        tips.append(
            {
                "icon": "✅",
                "title": "Planner Momentum",
                "body": f"You completed {completed_tasks} planner task(s). Keep the streak moving with a short review block.",
            }
        )

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
    quiz_completed = sum(1 for entry in ACTIVITY_LOG if entry["kind"] == "quiz_completed")
    topic_summary = _topic_summary()
    mastered_topics = sum(1 for topic in topic_summary if topic["pct"] >= 80)
    mastery = min(99, len(ACTIVITY_LOG) * 2 + mastered_topics * 3)

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

    recent_quizzes = _recent_quizzes()
    tips = _tips_from_activity()

    return {
        "user": {**USER_PROFILE, "streak": streak},
        "kpis": [
            {
                "id": "mastery",
                "icon": "🎯",
                "label": "Average Mastery",
                "value": str(mastery),
                "suffix": "%",
                "delta": "↑ improving from activity" if ACTIVITY_LOG else "No activity yet",
                "positive": True,
                "link": "quiz",
            },
            {
                "id": "topics",
                "icon": "📚",
                "label": "Topics Mastered",
                "value": str(mastered_topics),
                "suffix": "/6",
                "delta": f"{max(0, 6 - mastered_topics)} topics remaining" if ACTIVITY_LOG else "Start studying to unlock progress",
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
                "delta": f"+{quiz_completed} from sessions" if ACTIVITY_LOG else "No quizzes completed yet",
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
    }
