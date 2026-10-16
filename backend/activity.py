from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any

from learner_model import build_topic_mastery
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

DATA_DIR = Path(__file__).resolve().parent / "data"
ACTIVITY_PATH = DATA_DIR / "activity_events.json"

def _load_activity() -> list[dict[str, Any]]:
    try:
        loaded = json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
        return [entry for entry in loaded if isinstance(entry, dict)] if isinstance(loaded, list) else []
    except (OSError, json.JSONDecodeError):
        return []

ACTIVITY_LOCK = threading.RLock()


def _save_activity() -> None:
    """Atomically persist events using a unique temp file (safe on Windows)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_DIR,
            prefix="activity_events_",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(ACTIVITY_LOG[-5000:], temporary, ensure_ascii=False, indent=2)
            temp_path = Path(temporary.name)
        os.replace(temp_path, ACTIVITY_PATH)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

# Only completed recommendation work contributes to activity totals/heatmap.
# Start and dismiss events remain visible in recent activity without inflating study activity.
STUDY_EVENT_KINDS = {"note_created", "note_view", "quiz_completed", "study_session_completed", "study_session", "planner_task_done", "upload_processed", "targeted_study_generated", "chat_message", "recommendation_completed"}
RECENT_ACTIVITY_KINDS = STUDY_EVENT_KINDS | {"recommendation_started", "recommendation_dismissed"}
STUDY_TZ = ZoneInfo("Asia/Kolkata")
ACTIVITY_LOG: list[dict[str, Any]] = _load_activity()
USER_PROFILE = deepcopy(BASE_USER)


def record_activity(kind: str, **payload: Any) -> dict[str, Any]:
    # Protect deduplication, list mutation and file replacement as one operation.
    with ACTIVITY_LOCK:
        event_id = payload.get("event_id") or payload.get("attempt_id")
        session_id = payload.get("session_id")
        if event_id:
            existing = next((e for e in ACTIVITY_LOG if event_id in (e.get("event_id"), e.get("attempt_id"))), None)
            if existing:
                return existing
        if session_id and not event_id:
            existing = next((e for e in ACTIVITY_LOG if e.get("kind") == kind and e.get("session_id") == session_id), None)
            if existing:
                return existing
        now = datetime.now(timezone.utc)
        entry = {
            "kind": kind,
            "timestamp": now.isoformat(timespec="seconds"),
            "event_id": event_id or f"{kind}:{now.timestamp()}:{len(ACTIVITY_LOG)}",
            **payload,
        }
        ACTIVITY_LOG.append(entry)
        if len(ACTIVITY_LOG) > 5000:
            del ACTIVITY_LOG[:-5000]
        _save_activity()
        return entry

def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(STUDY_TZ)
    except (TypeError, ValueError, OverflowError):
        return None


def _unique_days() -> list[date]:
    days = set()
    for entry in ACTIVITY_LOG:
        if entry.get("kind") not in STUDY_EVENT_KINDS:
            continue
        parsed = _parse_dt(entry.get("timestamp"))
        if parsed:
            days.add(parsed.date())
    return sorted(days)

def _streak_from_days(days: list[date]) -> int:
    if not days:
        return 0

    day_set = set(days)
    streak = 0
    cursor = datetime.now(STUDY_TZ).date()
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _normalize_topic_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _topic_summary(topic_mastery: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Render only topics that have actual persisted quiz evidence."""
    if not topic_mastery:
        return []
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
            trend = float(stats.get("trend") or 0.0)
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
        trend = float(stats.get("trend") or 0.0)
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


def _study_seconds_from_activity(start_day: date | None = None, end_day: date | None = None) -> int:
    """Sum deduplicated active intervals, intersected with inclusive IST calendar-day bounds."""
    total_seconds = 0.0
    seen: set[str] = set()
    now = datetime.now(STUDY_TZ)
    window_start = datetime.combine(start_day, time.min, tzinfo=STUDY_TZ) if start_day else None
    window_end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=STUDY_TZ) if end_day else None
    for entry in ACTIVITY_LOG:
        if entry.get("kind") != "study_session_completed":
            continue
        identity = str(entry.get("session_id") or entry.get("event_id") or "")
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        intervals = entry.get("intervals")
        parsed_intervals: list[tuple[datetime, datetime]] = []
        if isinstance(intervals, list):
            for interval in intervals:
                if not isinstance(interval, dict):
                    continue
                left, right = _parse_dt(interval.get("started_at")), _parse_dt(interval.get("ended_at"))
                if left and right and right > left:
                    parsed_intervals.append((left, right))
        # Backward compatibility for sessions recorded before interval tracking existed.
        if not parsed_intervals:
            started = _parse_dt(entry.get("started_at") or entry.get("start_time"))
            ended = _parse_dt(entry.get("ended_at") or entry.get("end_time"))
            if started and ended and ended > started:
                parsed_intervals.append((started, min(ended, started + timedelta(hours=24))))
            elif entry.get("duration_seconds") is not None:
                stamp = _parse_dt(entry.get("timestamp"))
                if not stamp or (start_day and stamp.date() < start_day) or (end_day and stamp.date() > end_day):
                    continue
                try:
                    total_seconds += max(0.0, min(float(entry["duration_seconds"]), 24 * 3600))
                except (TypeError, ValueError, OverflowError):
                    continue
                continue
        for started, ended in parsed_intervals:
            left = max(started, window_start) if window_start else started
            right = min(ended, window_end) if window_end else min(ended, now)
            if right > left:
                total_seconds += (right - left).total_seconds()
    return int(total_seconds)


def _study_minutes_from_activity(start_day: date | None = None, end_day: date | None = None) -> int:
    """Whole-minute display helper; calculations retain second precision until presentation."""
    return _study_seconds_from_activity(start_day, end_day) // 60

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


def _pending_revision_tasks() -> list[dict[str, Any]]:
    """Return only saved, unfinished planner tasks; do not infer from templates."""
    path = DATA_DIR / "revision_tasks.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(saved, list):
        return []
    return [
        task for task in saved
        if isinstance(task, dict) and task.get("id") is not None and not task.get("done")
    ]


def _tips_from_activity(
    attempts: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tips: list[dict[str, Any]] = []
    latest_upload = next(
        (entry for entry in reversed(ACTIVITY_LOG) if entry.get("kind") == "upload_processed"),
        None,
    )
    completed_tasks = sum(
        1 for entry in ACTIVITY_LOG
        if entry.get("kind") == "planner_task_done" and entry.get("done")
    )

    # Personalized learning recommendations are exposed separately as structured
    # records. This legacy tips field remains for activity/planner nudges only.
    pending_tasks = _pending_revision_tasks()
    if pending_tasks and len(tips) < 3:
        next_task = pending_tasks[0]
        tips.append({
            "icon": "📅",
            "title": "Pending revision task",
            "body": f"Continue with {next_task.get('title', 'your next revision task')} ({next_task.get('topic', 'General')}). It is still marked incomplete in your saved planner.",
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
    # Preserve event-count intensity for ordinary activity. A measured study session
    # contributes one activity to every local day on which an active interval occurred.
    counts = Counter()
    seen_sessions: set[str] = set()
    for entry in ACTIVITY_LOG:
        if entry.get("kind") not in STUDY_EVENT_KINDS:
            continue
        try:
            if entry.get("kind") == "study_session_completed":
                session_id = str(entry.get("session_id") or entry.get("event_id") or "")
                if session_id and session_id in seen_sessions:
                    continue
                if session_id:
                    seen_sessions.add(session_id)
                intervals = entry.get("intervals")
                days_for_session: set[date] = set()
                if isinstance(intervals, list):
                    for interval in intervals:
                        if not isinstance(interval, dict):
                            continue
                        left, right = _parse_dt(interval.get("started_at")), _parse_dt(interval.get("ended_at"))
                        if not left or not right or right <= left:
                            continue
                        cursor = left.date()
                        last = (right - timedelta(microseconds=1)).date()
                        while cursor <= last:
                            days_for_session.add(cursor)
                            cursor += timedelta(days=1)
                # Legacy session events did not store active intervals.
                if not days_for_session:
                    parsed = _parse_dt(entry.get("timestamp"))
                    if parsed:
                        days_for_session.add(parsed.date())
                for session_day in days_for_session:
                    counts[session_day] += 1
                continue
            parsed = _parse_dt(entry.get("timestamp"))
            if parsed:
                counts[parsed.date()] += 1
        except (ValueError, TypeError, KeyError, OverflowError):
            continue

    today = datetime.now(STUDY_TZ).date()
    # The UI labels rows Monday through Sunday, so the first cell must be Monday.
    # Start at Monday 17 (for an 18-week view) weeks before this week,
    # ending on the current Sunday so the grid aligns with weekday labels.
    start = today - timedelta(days=today.weekday() + (weeks - 1) * 7)
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
    # Load note metadata lazily to avoid coupling event logging to note-generation services.
    from note_store import list_notes

    notes_count = sum(1 for note in list_notes() if note.get("source") == "generated")
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
    from recommendation_store import refresh_recommendations
    recommendations = refresh_recommendations(attempts=attempts, limit=3)
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

    completed_activities = sum(
        1 for entry in ACTIVITY_LOG
        if entry.get("kind") in {"quiz_completed", "study_session_completed", "planner_task_done", "recommendation_completed"}
    )

    activity_breakdown = Counter()
    for entry in ACTIVITY_LOG:
        kind = entry.get("kind")
        if kind == "quiz_completed":
            activity_breakdown["quiz_practice"] += 1
        elif kind in {"upload_processed", "targeted_study_generated", "note_created"}:
            activity_breakdown["notes_uploads"] += 1
        elif kind in {"note_view", "study_session_completed", "planner_task_done", "chat_message", "recommendation_completed"}:
            activity_breakdown["other"] += 1

    month_counts = Counter()
    for entry in ACTIVITY_LOG:
        if entry.get("kind") not in STUDY_EVENT_KINDS:
            continue
        try:
            dt = _parse_dt(entry.get("timestamp"))
            if dt:
                month_counts[(dt.year, dt.month)] += 1
        except (ValueError, TypeError, KeyError):
            continue

    today = datetime.now(STUDY_TZ).date().replace(day=1)
    months = []
    for offset in range(-11, 1):
        months.append(_add_months(today, offset))

    bar_chart = []
    for month in months:
        event_count = month_counts.get((month.year, month.month), 0)
        bar_chart.append({"month": month.strftime("%b"), "value": min(100, event_count)})

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
                "delta": "From recorded study-session durations" if study_minutes else "No timed study sessions recorded",
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
            "total_activities": f"{sum(1 for e in ACTIVITY_LOG if e.get('kind') in STUDY_EVENT_KINDS):,}",
            "longest_streak": f"{streak} days",
            "active_days": len(days),
        },
        "bar_chart": bar_chart,
        "recent_quizzes": recent_quizzes,
        "tips": tips,
        "recommendations": recommendations,
        "heatmap_weeks": 18,
        "activity_heatmap": _activity_heatmap(18),
        "recent_activity": list(reversed([e for e in ACTIVITY_LOG if e.get("kind") in RECENT_ACTIVITY_KINDS][-8:])),
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
            "study_minutes_today": _study_minutes_from_activity(datetime.now(STUDY_TZ).date(), datetime.now(STUDY_TZ).date()),
            "study_minutes_week": _study_minutes_from_activity(datetime.now(STUDY_TZ).date() - timedelta(days=6), datetime.now(STUDY_TZ).date()),
            "notes_count": notes_count,
            "activity_breakdown": dict(activity_breakdown),
            "completed_activities": completed_activities,
            "topics_mastered": mastered_topics,
            "emoji_performance_history": emoji_history[:8],
        },
    }
