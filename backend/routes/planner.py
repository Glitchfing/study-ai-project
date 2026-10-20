from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from activity import ACTIVITY_LOG, record_activity
from learner_model import build_topic_mastery
from quiz_attempt_store import list_quiz_attempts

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TASKS_PATH = DATA_DIR / "revision_tasks.json"
PREFERENCES_PATH = DATA_DIR / "planner_preferences.json"
_LOCK = threading.RLock()
from scheduling_config import (
    PRIORITY_WEIGHTS as _PRIORITY_WEIGHTS,
    DEFAULT_DURATIONS as _DURATION_MINUTES,
    DEFAULT_DAILY_MINUTES,
    DEFAULT_PLANNING_DAYS,
    DEFAULT_START_HOUR,
    DEFAULT_END_HOUR,
    MASTERY_THRESHOLDS,
)

STUDY_TZ = ZoneInfo("Asia/Kolkata")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _save_json_atomic(path: Path, value: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _load_tasks() -> list[dict[str, Any]]:
    value = _load_json(TASKS_PATH, [])
    return [item for item in value if isinstance(item, dict) and "id" in item] if isinstance(value, list) else []


def _tracked_topics(attempts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Combine measured quiz topics with generated-note metadata that is not assessed yet."""
    measured = build_topic_mastery(attempts)
    topics: dict[str, dict[str, Any]] = {}
    for name, stats in measured.items():
        row = dict(stats)
        row.setdefault("topic", name)
        row.setdefault("note_id", None)
        row["evidence_source"] = "quiz"
        topics[name] = row

    # Generated notes are legitimate candidates for an initial review/diagnostic,
    # but static demo notes are intentionally excluded.
    try:
        from note_store import list_notes
        notes = list_notes()
    except Exception:
        notes = []

    def normalized(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")

    for note in notes:
        if not isinstance(note, dict) or note.get("source") != "generated":
            continue
        name = str(note.get("topic") or note.get("title") or "").strip()
        key = normalized(name)
        if not name or not key:
            continue
        matched_name = next((known for known in topics if normalized(known) == key), None)
        if matched_name:
            if not topics[matched_name].get("note_id"):
                topics[matched_name]["note_id"] = note.get("id")
            continue
        topics[name] = {
            "topic": name,
            "mastery": None,
            "mastery_pct": None,
            "trend": None,
            "trend_label": "insufficient_data",
            "attempts": 0,
            "last_reviewed_at": None,
            "evidence_confidence": 0.0,
            "note_id": note.get("id"),
            "evidence_source": "generated_note",
        }
    return topics


TASKS: list[dict[str, Any]] = _load_tasks()


def _persist_tasks() -> None:
    _save_json_atomic(TASKS_PATH, TASKS)


class TaskToggle(BaseModel):
    task_id: int | str
    done: bool


class TaskEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=1, max_length=120)
    priority: Literal["high", "med", "low"] | None = None
    est: str | None = Field(default=None, min_length=1, max_length=40)
    day: Literal["today", "upcoming"] | None = None
    date: str | None = Field(default=None, max_length=80)
    scheduled_at: str | None = None
    due_date: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=240)
    status: Literal["planned", "in_progress", "completed", "skipped", "missed", "cancelled"] | None = None


class PlannerPreferences(BaseModel):
    daily_minutes: int = Field(default=DEFAULT_DAILY_MINUTES, ge=15, le=600)
    planning_days: int = Field(default=DEFAULT_PLANNING_DAYS, ge=1, le=60)
    preferred_start_hour: int = Field(default=DEFAULT_START_HOUR, ge=0, le=23)
    preferred_end_hour: int = Field(default=DEFAULT_END_HOUR, ge=1, le=24)
    available_days: list[int] = Field(default_factory=lambda: list(range(7)))
    topic_importance: dict[str, float] = Field(default_factory=dict)
    deadlines: list[dict[str, Any]] = Field(default_factory=list)


def _task_done(task: dict[str, Any]) -> bool:
    return bool(task.get("done")) or task.get("status") == "completed"


def _parse_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _task_timestamp(task: dict[str, Any]) -> datetime | None:
    return _parse_datetime(task.get("scheduled_at") or task.get("due_date"))


def _deadline_timestamp(task: dict[str, Any]) -> datetime | None:
    """Prioritize the original due date when reporting overdue work."""
    return _parse_datetime(task.get("original_due_date") or task.get("due_date") or task.get("scheduled_at"))


def _duration(task: dict[str, Any]) -> int:
    explicit = task.get("duration_minutes")
    if isinstance(explicit, (int, float)) and not isinstance(explicit, bool) and explicit > 0:
        return int(explicit)
    match = re.search(r"(\d+)\s*min", str(task.get("est") or ""), re.I)
    if match:
        return max(5, int(match.group(1)))
    match = re.search(r"(\d+)\s*h", str(task.get("est") or ""), re.I)
    return int(match.group(1)) * 60 if match else 20


def _priority_label(score: float) -> str:
    return "high" if score >= .68 else "med" if score >= .40 else "low"


def calculate_priority(topic: dict[str, Any], *, now: datetime, due_at: datetime | None, importance: float = 0.5, overdue: bool = False) -> tuple[float, dict[str, float]]:
    mastery = topic.get("mastery")
    weakness = max(0.0, min(1.0, 1 - float(mastery))) if isinstance(mastery, (int, float)) else 0.0
    trend = topic.get("trend_label")
    decline = min(1.0, abs(float(topic.get("trend") or 0)) / .5) if trend == "declining" else 0.0
    if due_at:
        hours = (due_at - now).total_seconds() / 3600
        urgency = 1.0 if hours < 0 or overdue else max(0.0, min(1.0, 1 - hours / (24 * 14)))
    else:
        urgency = 0.0
    uncertainty = max(0.0, 1 - float(topic.get("evidence_confidence") or 0)) if mastery is not None else 1.0
    factors = {"weakness": weakness, "decline": decline, "urgency": urgency, "importance": max(0.0, min(1.0, importance)), "uncertainty": uncertainty}
    available = {key: val for key, val in factors.items() if key not in {"weakness", "decline"} or topic.get("mastery") is not None}
    denominator = sum(_PRIORITY_WEIGHTS[key] for key in available)
    score = sum(_PRIORITY_WEIGHTS[key] * val for key, val in available.items()) / denominator if denominator else 0.0
    return round(score, 4), factors


def _read_preferences() -> dict[str, Any]:
    saved = _load_json(PREFERENCES_PATH, {})
    return saved if isinstance(saved, dict) else {}


def _write_preferences(values: dict[str, Any]) -> None:
    _save_json_atomic(PREFERENCES_PATH, values)


def _candidate_topics() -> list[dict[str, Any]]:
    attempts = list_quiz_attempts(limit=1000)
    mastery = _tracked_topics(attempts)
    candidates = []
    preferences = _read_preferences()
    importance_map = preferences.get("topic_importance") or {}
    now = _utc_now()
    for name, stats in mastery.items():
        due_at = None
        for deadline in preferences.get("deadlines") or []:
            if not isinstance(deadline, dict):
                continue
            target = str(deadline.get("topic") or deadline.get("text") or "").strip().lower()
            if target and (target == name.lower() or name.lower() in target or target in name.lower()):
                due_at = _task_timestamp({"due_date": deadline.get("date")})
                break
        topic_key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        overdue_task = next((
            task for task in TASKS
            if not _task_done(task)
            and re.sub(r"[^a-z0-9]+", "-", str(task.get("topic") or "").lower()).strip("-") == topic_key
            and _deadline_timestamp(task) is not None
            and _deadline_timestamp(task) < now
        ), None)
        priority, factors = calculate_priority(
            stats, now=now, due_at=due_at, importance=float(importance_map.get(name, .5)),
            overdue=overdue_task is not None,
        )
        # Low-confidence topics receive a short diagnostic, not a false weak label.
        if stats.get("mastery") is None:
            kind, title, minutes = "assessment", f"Assess understanding: {name}", _DURATION_MINUTES["assessment"]
        elif float(stats["mastery"]) < MASTERY_THRESHOLDS["needs_practice"] or stats.get("trend_label") == "declining":
            kind, title, minutes = "targeted_practice", f"Targeted revision: {name}", _DURATION_MINUTES["targeted_practice"]
        elif float(stats["mastery"]) < MASTERY_THRESHOLDS["strong"]:
            kind, title, minutes = "deep_revision", f"Review topic: {name}", _DURATION_MINUTES["deep_revision"]
        else:
            kind, title, minutes = "quick_review", f"Spaced review: {name}", _DURATION_MINUTES["quick_review"]
        explanation_parts = []
        if stats.get("mastery") is not None:
            explanation_parts.append(f"measured mastery {round(stats['mastery'] * 100)}%")
        if stats.get("trend_label") == "declining":
            explanation_parts.append("recent performance is declining")
        if overdue_task:
            explanation_parts.append("an existing task for this topic is overdue")
        if due_at:
            explanation_parts.append("the user-provided deadline has passed; schedule catch-up revision" if due_at < now else "a matching user-provided deadline is relevant")
        if stats.get("mastery") is None:
            explanation_parts.append("assessment evidence is insufficient; use a diagnostic")
        candidates.append({
            "topic": name, "stats": stats, "priority_score": priority, "factors": factors,
            "activity_type": kind, "title": title, "duration_minutes": minutes,
            "reason": "; ".join(explanation_parts) or "Prioritized using the available learning evidence.",
            "due_at": due_at,
            "note_id": stats.get("note_id"),
        })
    return sorted(candidates, key=lambda item: (-item["priority_score"], item["due_at"] or datetime.max.replace(tzinfo=timezone.utc)))


def _eligible_slots(prefs: dict[str, Any], now: datetime, horizon: int) -> list[datetime]:
    start_hour = int(prefs.get("preferred_start_hour", 18))
    end_hour = int(prefs.get("preferred_end_hour", 22))
    if end_hour <= start_hour:
        end_hour = min(24, start_hour + 2)
    slots: list[datetime] = []
    local_now = now.astimezone(STUDY_TZ)
    available_days = {int(value) for value in prefs.get("available_days", range(7)) if str(value).lstrip("-").isdigit() and 0 <= int(value) <= 6}
    for offset in range(horizon):
        day = (local_now + timedelta(days=offset)).date()
        if day.weekday() not in available_days:
            continue
        cursor = datetime.combine(day, time(hour=start_hour), tzinfo=local_now.tzinfo)
        end_day = day + timedelta(days=1) if end_hour == 24 else day
        end = datetime.combine(end_day, time(hour=end_hour % 24), tzinfo=local_now.tzinfo)
        if offset == 0:
            base = now.astimezone(local_now.tzinfo).replace(second=0, microsecond=0)
            minutes_to_next_slot = 5 - (base.minute % 5)
            next_slot = base + timedelta(minutes=minutes_to_next_slot)
            cursor = max(cursor, next_slot)
        while cursor + timedelta(minutes=5) <= end:
            slots.append(cursor.astimezone(timezone.utc))
            cursor += timedelta(minutes=5)
    return slots


def _scheduled_timestamp(task: dict[str, Any]) -> datetime | None:
    """Parse a scheduled slot only; deadlines are not calendar occupancy."""
    raw = task.get("scheduled_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _overlap(start: datetime, duration: int, task: dict[str, Any]) -> bool:
    other = _scheduled_timestamp(task)
    if not other:
        return False
    other_duration = _duration(task)
    return start < other + timedelta(minutes=other_duration) and other < start + timedelta(minutes=duration)


@router.get("")
def get_planner(start: str | None = Query(None), end: str | None = Query(None)):
    with _LOCK:
        tasks = [dict(task) for task in TASKS]
    for task in tasks:
        task.setdefault("status", "completed" if _task_done(task) else "planned")
        task.setdefault("duration_minutes", _duration(task))
        task.setdefault("topic_id", re.sub(r"[^a-z0-9]+", "-", str(task.get("topic") or "").lower()).strip("-") or None)
    if start or end:
        def in_range(task: dict[str, Any]) -> bool:
            stamp = _task_timestamp(task)
            if stamp is None:
                return True
            return (not start or stamp.date().isoformat() >= start[:10]) and (not end or stamp.date().isoformat() <= end[:10])
        tasks = [task for task in tasks if in_range(task)]
    attempts = list_quiz_attempts(limit=1000)
    topics = list(_tracked_topics(attempts).values())
    events = []
    for item in ACTIVITY_LOG[-300:]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind in {"quiz_completed", "note_view", "study_session_completed", "planner_task_done", "planner_task_edited"}:
            events.append({"id": str(item.get("id") or uuid4()), "type": kind, "title": item.get("title") or item.get("topic_label") or kind.replace("_", " ").title(), "topic": item.get("topic") or item.get("topic_label"), "timestamp": item.get("created_at") or item.get("timestamp") or item.get("ended_at"), "status": "completed", "source": "activity", "task_id": item.get("revision_task_id") or item.get("task_id"), "duration_seconds": item.get("duration_seconds"), "duration_minutes": round(int(item.get("duration_seconds") or 0) / 60) if item.get("duration_seconds") is not None else None})
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        attempt_id = attempt.get("id")
        attempt_topic = str(attempt.get("topic") or attempt.get("topic_label") or attempt.get("note_title") or "").strip()
        attempt_time = _parse_datetime(attempt.get("created_at"))
        if attempt_time is None:
            continue
        already_logged = any(
            event.get("type") == "quiz_completed"
            and (
                (attempt_id is not None and str(event.get("attempt_id")) == str(attempt_id))
                or (
                    str(event.get("topic") or "").strip().lower() == attempt_topic.lower()
                    and (logged_time := _parse_datetime(event.get("timestamp"))) is not None
                    and abs((logged_time - attempt_time).total_seconds()) <= 120
                )
            )
            for event in events
        )
        if not already_logged:
            events.append({
                "id": f"quiz-{attempt_id}" if attempt_id is not None else f"quiz-{attempt_time.isoformat()}",
                "type": "quiz_completed",
                "title": attempt.get("note_title") or attempt.get("topic_label") or attempt_topic or "Quiz completed",
                "topic": attempt_topic or None,
                "timestamp": attempt_time.isoformat(timespec="seconds"),
                "status": "completed",
                "source": "quiz",
                "score": attempt.get("score"),
                "correct": attempt.get("correct"),
                "total": attempt.get("total"),
                "attempt_id": attempt_id,
            })
    for task in tasks:
        events.append({"id": f"task-{task['id']}", "type": "revision", "title": task.get("title"), "topic": task.get("topic"), "timestamp": task.get("scheduled_at") or task.get("due_date"), "status": task.get("status"), "source": "planner", "task_id": task.get("id"), "priority": task.get("priority"), "duration_minutes": task.get("duration_minutes"), "reason": task.get("priority_reason")})
    preferences = _read_preferences()
    deadlines = preferences.get("deadlines") or []
    for index, deadline in enumerate(deadlines):
        if not isinstance(deadline, dict) or not deadline.get("date"):
            continue
        topic = deadline.get("topic") or ""
        events.append({
            "id": f"deadline-{index}-{re.sub(r'[^a-z0-9]+', '-', str(topic).lower()).strip('-')}",
            "type": "deadline",
            "title": deadline.get("text") or f"Deadline: {topic or 'Assessment'}",
            "topic": topic or None,
            "timestamp": deadline.get("date"),
            "status": "planned",
            "source": "deadline",
        })
    events.sort(key=lambda item: str(item.get("timestamp") or ""))
    return {
        "tasks": tasks, "deadlines": deadlines, "topics": topics, "events": events,
        "preferences": {**{"daily_minutes": DEFAULT_DAILY_MINUTES, "planning_days": DEFAULT_PLANNING_DAYS, "preferred_start_hour": DEFAULT_START_HOUR, "preferred_end_hour": DEFAULT_END_HOUR, "available_days": list(range(7)), "topic_importance": {}}, **preferences},
        "summary": {
            "topics_tracked": len(topics),
            "topics_needing_revision": sum(1 for topic in topics if (isinstance(topic.get("mastery"), (int, float)) and topic["mastery"] < .7) or topic.get("trend_label") == "declining"),
            "upcoming_sessions": sum(1 for task in tasks if not _task_done(task) and task.get("status") not in {"cancelled", "skipped"} and _scheduled_timestamp(task) and _scheduled_timestamp(task) >= _utc_now()),
            "overdue_tasks": sum(1 for task in tasks if not _task_done(task) and task.get("status") not in {"cancelled", "skipped"} and _deadline_timestamp(task) and _deadline_timestamp(task) < _utc_now()),
            "completed_milestones": sum(1 for task in tasks if _task_done(task)),
        },
    }


@router.get("/preferences")
def get_preferences():
    saved = _read_preferences()
    return {**{"daily_minutes": DEFAULT_DAILY_MINUTES, "planning_days": DEFAULT_PLANNING_DAYS, "preferred_start_hour": DEFAULT_START_HOUR, "preferred_end_hour": DEFAULT_END_HOUR, "topic_importance": {}, "deadlines": []}, **saved}


@router.put("/preferences")
def update_preferences(body: PlannerPreferences):
    values = body.model_dump()
    if values["preferred_end_hour"] <= values["preferred_start_hour"]:
        raise HTTPException(status_code=400, detail="Preferred end hour must be after preferred start hour.")
    if not values["available_days"] or any(day < 0 or day > 6 for day in values["available_days"]):
        raise HTTPException(status_code=400, detail="Select at least one valid study day (Monday=0 through Sunday=6).")
    for deadline in values.get("deadlines") or []:
        if not isinstance(deadline, dict) or not str(deadline.get("topic") or "").strip():
            raise HTTPException(status_code=400, detail="Each deadline must include a related topic.")
        if _parse_datetime(deadline.get("date")) is None:
            raise HTTPException(status_code=400, detail="Each deadline must include a valid ISO date or datetime.")
    with _LOCK:
        _write_preferences(values)
    return {"preferences": values, "saved": True}


@router.post("/auto-schedule")
def auto_schedule():
    with _LOCK:
        now = _utc_now()
        prefs = {**{"daily_minutes": DEFAULT_DAILY_MINUTES, "planning_days": DEFAULT_PLANNING_DAYS, "preferred_start_hour": DEFAULT_START_HOUR, "preferred_end_hour": DEFAULT_END_HOUR, "topic_importance": {}, "deadlines": []}, **_read_preferences()}
        topics = _candidate_topics()
        existing = [dict(task) for task in TASKS]
        # Prefer to reuse existing generated tasks with a matching topic. Preserve manual tasks.
        pending_generated: dict[str, dict[str, Any]] = {}
        for task in existing:
            if task.get("origin") == "auto" and not _task_done(task) and task.get("status") != "in_progress" and task.get("status") != "cancelled" and task.get("status") != "skipped" and not task.get("schedule_locked"):
                pending_generated.setdefault(str(task.get("topic_id") or task.get("topic") or "").lower(), task)
        slots = _eligible_slots(prefs, now, int(prefs["planning_days"]))
        retained, created, rescheduled, unscheduled = 0, 0, 0, []
        current = [task for task in existing if not _task_done(task) and task.get("status") not in {"cancelled", "skipped"}]
        candidate_topic_ids = {re.sub(r"[^a-z0-9]+", "-", str(item["topic"]).lower()).strip("-") for item in topics}
        pending_ids = {task.get("id") for key, task in pending_generated.items() if key in candidate_topic_ids}
        occupied = [task for task in current if task.get("id") not in pending_ids]
        planned_today: dict[str, int] = {}
        updated_tasks = [dict(task) for task in existing]
        for reserved_task in occupied:
            reserved_at = _scheduled_timestamp(reserved_task)
            if reserved_at:
                day_key = reserved_at.astimezone(STUDY_TZ).date().isoformat()
                planned_today[day_key] = planned_today.get(day_key, 0) + _duration(reserved_task)
        for candidate in topics:
            topic = candidate["topic"]
            topic_id = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
            key = topic_id.lower()
            task = pending_generated.get(key)
            if task:
                idx = next((i for i, row in enumerate(updated_tasks) if row.get("id") == task.get("id")), None)
                if idx is not None:
                    updated_tasks[idx]["priority_score"] = candidate["priority_score"]
                    updated_tasks[idx]["priority"] = _priority_label(candidate["priority_score"])
                    updated_tasks[idx]["priority_reason"] = candidate["reason"]
                    updated_tasks[idx]["evidence"] = {"mastery": candidate["stats"].get("mastery"), "trend": candidate["stats"].get("trend_label"), "factors": candidate["factors"]}
                    task = updated_tasks[idx]
            else:
                task = None
                # A pending manual task already covers this topic; enrich its evidence,
                # but never create a duplicate automatic task or overwrite its chosen slot.
                manual_match = next((
                    item for item in current
                    if (item.get("origin") != "auto" or item.get("status") == "in_progress" or item.get("schedule_locked"))
                    and re.sub(r"[^a-z0-9]+", "-", str(item.get("topic") or "").lower()).strip("-") == topic_id
                ), None)
                if manual_match:
                    manual_index = next((i for i, row in enumerate(updated_tasks) if row.get("id") == manual_match.get("id")), None)
                    if manual_index is not None:
                        updated_tasks[manual_index]["priority_score"] = candidate["priority_score"]
                        updated_tasks[manual_index]["priority"] = _priority_label(candidate["priority_score"])
                        updated_tasks[manual_index]["priority_reason"] = candidate["reason"]
                        updated_tasks[manual_index]["evidence"] = {"mastery": candidate["stats"].get("mastery"), "trend": candidate["stats"].get("trend_label"), "factors": candidate["factors"]}
                    retained += 1
                    continue
            chosen = None
            duration = candidate["duration_minutes"]
            for slot in slots:
                local_slot = slot.astimezone(STUDY_TZ)
                if planned_today.get(local_slot.date().isoformat(), 0) + duration > int(prefs["daily_minutes"]):
                    continue
                end_hour = int(prefs.get("preferred_end_hour", DEFAULT_END_HOUR))
                window_end_day = local_slot.date() + timedelta(days=1) if end_hour == 24 else local_slot.date()
                window_end = datetime.combine(window_end_day, time(hour=end_hour % 24), tzinfo=STUDY_TZ)
                if local_slot + timedelta(minutes=duration) > window_end:
                    continue
                if candidate["due_at"] and candidate["due_at"] >= now and slot + timedelta(minutes=duration) > candidate["due_at"]:
                    continue
                if any(_overlap(slot, duration, other) for other in occupied):
                    continue
                chosen = slot
                break
            if chosen is None:
                unscheduled.append({"topic": topic, "reason": "No slot fits the daily time budget, available time window, existing tasks, and applicable deadline."})
                if task is not None:
                    # Keep existing generated work instead of silently dropping it.
                    occupied.append(task)
                    old_slot = _scheduled_timestamp(task)
                    if old_slot:
                        old_day = old_slot.astimezone(STUDY_TZ).date().isoformat()
                        planned_today[old_day] = planned_today.get(old_day, 0) + _duration(task)
                continue
            if task is None:
                max_id = max([int(t.get("id")) for t in updated_tasks if str(t.get("id", "")).isdigit()] or [0])
                task = {
                    "id": max_id + 1, "title": candidate["title"], "topic": topic, "topic_id": topic_id,
                    "priority": _priority_label(candidate["priority_score"]), "priority_score": candidate["priority_score"],
                    "priority_reason": candidate["reason"], "evidence": {"mastery": candidate["stats"].get("mastery"), "trend": candidate["stats"].get("trend_label"), "factors": candidate["factors"]},
                    "activity_type": candidate["activity_type"], "est": f"{duration} min", "duration_minutes": duration,
                    "note_id": candidate.get("note_id"),
                    "done": False, "status": "planned", "origin": "auto", "created_at": now.isoformat(timespec="seconds"),
                    "original_due_date": candidate["due_at"].isoformat(timespec="seconds") if candidate["due_at"] else None,
                }
                updated_tasks.append(task)
                created += 1
            else:
                old = _scheduled_timestamp(task)
                if old and old != chosen:
                    task.setdefault("reschedule_history", []).append({"from": old.isoformat(timespec="seconds"), "to": chosen.isoformat(timespec="seconds"), "at": now.isoformat(timespec="seconds"), "reason": "Schedule refreshed using latest learning evidence and availability."})
                    rescheduled += 1
                else:
                    # Reusing the same task record is retained work, even without a previous slot.
                    retained += 1
                task["title"] = candidate["title"]
                task["priority_score"] = candidate["priority_score"]
                task["priority"] = _priority_label(candidate["priority_score"])
                task["priority_reason"] = candidate["reason"]
                task["evidence"] = {"mastery": candidate["stats"].get("mastery"), "trend": candidate["stats"].get("trend_label"), "factors": candidate["factors"]}
                task["activity_type"] = candidate["activity_type"]
                task["note_id"] = candidate.get("note_id") or task.get("note_id")
            # Shared scheduling fields must be persisted for both created and reused tasks.
            task["duration_minutes"] = duration
            task["est"] = f"{duration} min"
            task["scheduled_at"] = chosen.isoformat(timespec="seconds")
            task["due_date"] = task.get("original_due_date") or (candidate["due_at"].isoformat(timespec="seconds") if candidate["due_at"] else None)
            task["day"] = "today" if chosen.astimezone(STUDY_TZ).date() == now.astimezone(STUDY_TZ).date() else "upcoming"
            task["date"] = chosen.astimezone(STUDY_TZ).strftime("%a, %d %b · %H:%M")
            task["updated_at"] = now.isoformat(timespec="seconds")
            previous_status = task.get("status") or "planned"
            if previous_status != "planned":
                task.setdefault("status_history", []).append({
                    "from": previous_status, "to": "planned", "at": now.isoformat(timespec="seconds"),
                    "reason": "Task returned to the plan after schedule regeneration.",
                })
            task["status"] = "planned"
            task["done"] = False
            planned_day = chosen.astimezone(STUDY_TZ).date().isoformat()
            planned_today[planned_day] = planned_today.get(planned_day, 0) + duration
            occupied.append(task)
        TASKS[:] = updated_tasks
        _persist_tasks()
        record_activity("planner_schedule_generated", created=created, rescheduled=rescheduled, retained=retained, unscheduled=len(unscheduled))
    return {
        "message": "Revision schedule generated and saved from your quiz history.",
        "created_count": created, "rescheduled_count": rescheduled, "retained_count": retained,
        "topics_considered": len(topics), "unscheduled": unscheduled,
        "generated_at": now.isoformat(timespec="seconds"), "tasks": [dict(task) for task in TASKS],
    }


@router.post("/toggle")
def toggle_task(body: TaskToggle):
    with _LOCK:
        task = next((item for item in TASKS if str(item.get("id")) == str(body.task_id)), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Revision task not found.")
        previous = _task_done(task)
        if previous != body.done:
            task["done"] = body.done
            task["status"] = "completed" if body.done else "planned"
            task["updated_at"] = _utc_now().isoformat(timespec="seconds")
            if body.done:
                task["completed_at"] = task["updated_at"]
            elif task.get("completed_at"):
                # Keep the original completion record; reopening does not erase history.
                task.setdefault("status_history", []).append({"status": "reopened", "at": task["updated_at"], "previous_completion": task["completed_at"]})
            _persist_tasks()
            record_activity("planner_task_done" if body.done else "planner_task_reopened", task_id=body.task_id, done=body.done, title=task.get("title"), topic=str(task.get("topic") or "").lower() or None)
        return {"task_id": body.task_id, "done": _task_done(task), "task": dict(task)}


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, changes: TaskEdit):
    with _LOCK:
        task = next((item for item in TASKS if str(item.get("id")) == str(task_id)), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Revision task not found.")
        updates = changes.model_dump(exclude_unset=True, exclude_none=True)
        now = _utc_now()
        now_text = now.isoformat(timespec="seconds")
        for date_key in ("scheduled_at", "due_date"):
            if date_key in updates and updates[date_key] and _parse_datetime(updates[date_key]) is None:
                raise HTTPException(status_code=400, detail=f"{date_key} must be an ISO date or datetime.")
        if "scheduled_at" in updates:
            task["schedule_locked"] = True
            old = _scheduled_timestamp(task)
            new_time = _parse_datetime(updates["scheduled_at"])
            if old and new_time and old != new_time:
                task.setdefault("reschedule_history", []).append({"from": old.isoformat(timespec="seconds"), "to": new_time.isoformat(timespec="seconds"), "at": now_text, "reason": "User rescheduled task."})
        if "status" in updates:
            new_status = updates["status"]
            if _task_done(task) and new_status != "completed":
                raise HTTPException(status_code=409, detail="Completed tasks cannot be reopened by editing status; use the task toggle action.")
            old_status = task.get("status") or ("completed" if _task_done(task) else "planned")
            if old_status != new_status:
                task.setdefault("status_history", []).append({"from": old_status, "to": new_status, "at": now_text})
        for key, value in updates.items():
            task[key] = value
        if "duration_minutes" in updates:
            task["est"] = f"{updates['duration_minutes']} min"
        if updates.get("status") == "completed":
            task["done"] = True
            task.setdefault("completed_at", now_text)
        elif updates.get("status") and not _task_done(task):
            task["done"] = False
        task["updated_at"] = now_text
        _persist_tasks()
        record_activity("planner_task_edited", task_id=task_id, title=task.get("title"), topic=str(task.get("topic") or "").lower() or None)
        return {"task": dict(task), "updated": bool(updates)}


@router.delete("/tasks/{task_id}")
def cancel_task(task_id: str):
    """Soft-cancel a revision task while keeping its timeline and session history."""
    with _LOCK:
        task = next((item for item in TASKS if str(item.get("id")) == str(task_id)), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Revision task not found.")
        if task.get("status") == "completed" or _task_done(task):
            raise HTTPException(status_code=409, detail="Completed tasks cannot be cancelled.")
        if task.get("status") == "cancelled":
            return {"task": dict(task), "cancelled": True, "already_cancelled": True}
        now_text = _utc_now().isoformat(timespec="seconds")
        old_status = task.get("status") or "planned"
        task.setdefault("status_history", []).append({"from": old_status, "to": "cancelled", "at": now_text})
        task["status"] = "cancelled"
        task["done"] = False
        task["cancelled_at"] = now_text
        task["updated_at"] = now_text
        _persist_tasks()
        record_activity("planner_task_cancelled", task_id=task_id, title=task.get("title"), topic=str(task.get("topic") or "").lower() or None)
        return {"task": dict(task), "cancelled": True}


@router.post("/tasks")
def create_task(payload: TaskEdit):
    data = payload.model_dump(exclude_none=True)
    if not data.get("title") or not data.get("topic"):
        raise HTTPException(status_code=400, detail="A task title and topic are required.")
    with _LOCK:
        max_id = max([int(t.get("id")) for t in TASKS if str(t.get("id", "")).isdigit()] or [0])
        now = _utc_now().isoformat(timespec="seconds")
        task = {"id": max_id + 1, "title": data["title"], "topic": data["topic"], "priority": data.get("priority", "med"), "est": data.get("est", "20 min"), "duration_minutes": data.get("duration_minutes", 20), "done": False, "status": "planned", "origin": "manual", "created_at": now, "scheduled_at": data.get("scheduled_at"), "due_date": data.get("due_date"), "day": data.get("day", "upcoming"), "date": data.get("date")}
        TASKS.append(task)
        _persist_tasks()
        return {"task": dict(task), "created": True}
