from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from activity import record_activity

router = APIRouter()


class TaskToggle(BaseModel):
    task_id: int
    done: bool


TASKS = [
    {"id": 1, "title": "Review Decision Trees",      "topic": "ML",  "priority": "high", "est": "15 min", "done": False, "day": "today",    "date": None},
    {"id": 2, "title": "NLP Quiz — Tokenization",    "topic": "NLP", "priority": "high", "est": "25 min", "done": False, "day": "today",    "date": None},
    {"id": 3, "title": "Read BERT Paper Summary",    "topic": "NLP", "priority": "med",  "est": "20 min", "done": False, "day": "today",    "date": None},
    {"id": 4, "title": "Linked List Revision",       "topic": "DS",  "priority": "low",  "est": "10 min", "done": False, "day": "today",    "date": None},
    {"id": 5, "title": "Neural Networks Intro",      "topic": "ML",  "priority": "med",  "est": "30 min", "done": False, "day": "today",    "date": None},
    {"id": 6, "title": "Graph Algorithms",           "topic": "DS",  "priority": "med",  "est": "45 min", "done": False, "day": "upcoming", "date": "Tomorrow"},
    {"id": 7, "title": "Dynamic Programming",        "topic": "DS",  "priority": "high", "est": "60 min", "done": False, "day": "upcoming", "date": "Mar 31"},
    {"id": 8, "title": "System Design Basics",       "topic": "SDE", "priority": "low",  "est": "30 min", "done": False, "day": "upcoming", "date": "Apr 1"},
]

DEADLINES = [
    {"text": "ML Assignment #3",  "date": "Apr 2",  "color": "#e29578"},
    {"text": "NLP Midterm Exam",  "date": "Apr 8",  "color": "#c1694f"},
    {"text": "DS Project Due",    "date": "Apr 15", "color": "#64b6ac"},
]

# In-memory done state (use a DB in production)
_done_set: set = set()


@router.get("")
def get_planner():
    """Return all tasks + deadlines."""
    tasks_out = []
    for t in TASKS:
        tasks_out.append({**t, "done": t["id"] in _done_set})
    return {"tasks": tasks_out, "deadlines": DEADLINES}


@router.post("/toggle")
def toggle_task(body: TaskToggle):
    """Toggle task completion."""
    if body.done:
        _done_set.add(body.task_id)
    else:
        _done_set.discard(body.task_id)
    task = next((task for task in TASKS if task["id"] == body.task_id), None)
    record_activity(
        "planner_task_done",
        task_id=body.task_id,
        done=body.done,
        title=task["title"] if task else None,
        topic=task["topic"].lower() if task else None,
    )
    return {"task_id": body.task_id, "done": body.task_id in _done_set}


@router.post("/auto-schedule")
def auto_schedule():
    """Stub: AI-generate an optimised study schedule."""
    return {
        "message": "Schedule optimised using spaced repetition!",
        "optimised_count": 5,
    }
