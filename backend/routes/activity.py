from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from activity import ACTIVITY_LOG, record_activity

router = APIRouter()


class ActivityEvent(BaseModel):
    kind: str
    topic: Optional[str] = None
    view: Optional[str] = None
    filename: Optional[str] = None
    note_id: Optional[str] = None
    format: Optional[str] = None
    score: Optional[int] = None
    total: Optional[int] = None
    message: Optional[str] = None
    task_id: Optional[int] = None
    done: Optional[bool] = None
    session_id: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    extra: dict[str, Any] = Field(default_factory=dict)


class StudySessionStart(BaseModel):
    topic: Optional[str] = Field(default=None, max_length=120)


class StudySessionComplete(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=80)


def _active_session() -> dict[str, Any] | None:
    completed = {
        event.get("session_id")
        for event in ACTIVITY_LOG
        if event.get("kind") == "study_session_completed"
    }
    for event in reversed(ACTIVITY_LOG):
        if event.get("kind") == "study_session_started" and event.get("session_id") not in completed:
            return event
    return None


@router.post("")
def log_activity(event: ActivityEvent):
    payload = event.model_dump(exclude={"kind", "extra"}, exclude_none=True)
    payload.update(event.extra or {})
    entry = record_activity(event.kind, **payload)
    return {"ok": True, "event": entry}


@router.get("/recent")
def recent_activity():
    return {"items": list(reversed(ACTIVITY_LOG[-20:]))}


@router.get("/study-sessions/active")
def get_active_study_session():
    """Restore an active timer after a browser refresh."""
    active = _active_session()
    return {"active": active}


@router.post("/study-sessions/start")
def start_study_session(payload: StudySessionStart):
    """Persist a single active study session with a server timestamp."""
    current = _active_session()
    if current:
        return {"session": current, "already_active": True}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    session = record_activity(
        "study_session_started",
        session_id=str(uuid4()),
        started_at=now,
        topic=payload.topic.strip() if payload.topic and payload.topic.strip() else None,
    )
    return {"session": session, "already_active": False}


@router.post("/study-sessions/complete")
def complete_study_session(payload: StudySessionComplete):
    """Record the end time once; the dashboard derives duration from the interval."""
    started = next(
        (
            event for event in ACTIVITY_LOG
            if event.get("kind") == "study_session_started"
            and event.get("session_id") == payload.session_id
        ),
        None,
    )
    if started is None:
        raise HTTPException(status_code=404, detail="Study session not found.")
    completed = next(
        (
            event for event in ACTIVITY_LOG
            if event.get("kind") == "study_session_completed"
            and event.get("session_id") == payload.session_id
        ),
        None,
    )
    if completed:
        return {"session": completed, "already_completed": True}

    ended_at = datetime.now(timezone.utc)
    started_at = datetime.fromisoformat(started["started_at"].replace("Z", "+00:00"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    duration_seconds = max(0, min(int((ended_at - started_at).total_seconds()), 86400))
    completed = record_activity(
        "study_session_completed",
        session_id=payload.session_id,
        started_at=started_at.isoformat(timespec="seconds"),
        ended_at=ended_at.isoformat(timespec="seconds"),
        duration_seconds=duration_seconds,
        topic=started.get("topic"),
    )
    return {"session": completed, "already_completed": False}
