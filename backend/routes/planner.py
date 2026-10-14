from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from activity import record_activity

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TASKS_PATH = DATA_DIR / "revision_tasks.json"

_DEFAULT_TASKS: list[dict[str, Any]] = [
    {"id": 1, "title": "Review Decision Trees", "topic": "ML", "priority": "high", "est": "15 min", "done": False, "day": "today", "date": None},
    {"id": 2, "title": "NLP Quiz — Tokenization", "topic": "NLP", "priority": "high", "est": "25 min", "done": False, "day": "today", "date": None},
    {"id": 3, "title": "Read BERT Paper Summary", "topic": "NLP", "priority": "med", "est": "20 min", "done": False, "day": "today", "date": None},
    {"id": 4, "title": "Linked List Revision", "topic": "DS", "priority": "low", "est": "10 min", "done": False, "day": "today", "date": None},
    {"id": 5, "title": "Neural Networks Intro", "topic": "ML", "priority": "med", "est": "30 min", "done": False, "day": "today", "date": None},
    {"id": 6, "title": "Graph Algorithms", "topic": "DS", "priority": "med", "est": "45 min", "done": False, "day": "upcoming", "date": "Tomorrow"},
    {"id": 7, "title": "Dynamic Programming", "topic": "DS", "priority": "high", "est": "60 min", "done": False, "day": "upcoming", "date": "Mar 31"},
    {"id": 8, "title": "System Design Basics", "topic": "SDE", "priority": "low", "est": "30 min", "done": False, "day": "upcoming", "date": "Apr 1"},
]

DEADLINES = [
    {"text": "ML Assignment #3", "date": "Apr 2", "color": "#e29578"},
    {"text": "NLP Midterm Exam", "date": "Apr 8", "color": "#c1694f"},
    {"text": "DS Project Due", "date": "Apr 15", "color": "#64b6ac"},
]


def _load_tasks() -> list[dict[str, Any]]:
    try:
        value = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
        if isinstance(value, list):
            loaded = [item for item in value if isinstance(item, dict) and "id" in item]
            if loaded:
                return loaded
    except (OSError, json.JSONDecodeError):
        pass
    return [dict(task) for task in _DEFAULT_TASKS]


def _save_tasks() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = TASKS_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(TASKS, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(TASKS_PATH)


TASKS: list[dict[str, Any]] = _load_tasks()


class TaskToggle(BaseModel):
    task_id: int
    done: bool


class TaskEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=1, max_length=100)
    priority: Literal["high", "med", "low"] | None = None
    est: str | None = Field(default=None, min_length=1, max_length=40)
    day: Literal["today", "upcoming"] | None = None
    date: str | None = Field(default=None, max_length=80)


@router.get("")
def get_planner():
    """Return persisted revision tasks and the existing deadline list."""
    return {"tasks": [dict(task) for task in TASKS], "deadlines": DEADLINES}


@router.post("/toggle")
def toggle_task(body: TaskToggle):
    task = next((item for item in TASKS if item.get("id") == body.task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Revision task not found.")

    previous = bool(task.get("done"))
    if previous != body.done:
        task["done"] = body.done
        task["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _save_tasks()
        # A completed task creates one activity event; repeating the same
        # toggle value is idempotent and does not inflate the heatmap.
        if body.done:
            record_activity(
                "planner_task_done",
                task_id=body.task_id,
                done=True,
                title=task.get("title"),
                topic=str(task.get("topic") or "").lower() or None,
            )
        else:
            record_activity(
                "planner_task_reopened",
                task_id=body.task_id,
                done=False,
                title=task.get("title"),
                topic=str(task.get("topic") or "").lower() or None,
            )
    return {"task_id": body.task_id, "done": bool(task.get("done"))}


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, changes: TaskEdit):
    """Persist supported edits to an existing revision task."""
    task = next((item for item in TASKS if item.get("id") == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail="Revision task not found.")

    updates = changes.model_dump(exclude_unset=True)
    if not updates:
        return {"task": dict(task), "updated": False}
    for key, value in updates.items():
        task[key] = value
    _save_tasks()
    record_activity(
        "planner_task_edited",
        task_id=task_id,
        title=task.get("title"),
        topic=str(task.get("topic") or "").lower() or None,
    )
    return {"task": dict(task), "updated": True}


@router.post("/auto-schedule")
def auto_schedule():
    """The current project exposes a placeholder auto-schedule operation."""
    return {
        "message": "Schedule auto-generation is not implemented yet.",
        "optimised_count": 0,
    }
