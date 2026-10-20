from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from activity import ACTIVITY_LOG, ACTIVITY_LOCK, STUDY_TZ, _save_activity, record_activity

router = APIRouter()
STALE_AFTER = timedelta(minutes=5)


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
    revision_task_id: Optional[int] = Field(default=None, ge=1)


class StudySessionAction(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=80)
    request_id: Optional[str] = Field(default=None, max_length=100)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _session_events(session_id: str) -> list[dict[str, Any]]:
    return [event for event in ACTIVITY_LOG if event.get("session_id") == session_id and str(event.get("kind", "")).startswith("study_session_")]


def _session_state(session_id: str) -> dict[str, Any] | None:
    events = _session_events(session_id)
    started = next((e for e in events if e.get("kind") == "study_session_started"), None)
    if not started:
        return None
    state: dict[str, Any] = {
        "session_id": session_id, "topic": started.get("topic"), "revision_task_id": started.get("revision_task_id"), "started_at": started.get("started_at"),
        "status": "active", "intervals": [], "active_interval_started_at": started.get("started_at"),
        "last_heartbeat_at": started.get("last_heartbeat_at") or started.get("started_at"),
        "duration_seconds": 0,
    }
    for event in events:
        kind = event.get("kind")
        if kind == "study_session_paused":
            interval = event.get("interval")
            if isinstance(interval, dict):
                state["intervals"].append(interval)
            state["status"] = "paused"
            state["active_interval_started_at"] = None
            state["paused_at"] = event.get("ended_at")
        elif kind == "study_session_resumed":
            state["status"] = "active"
            state["active_interval_started_at"] = event.get("resumed_at")
            state["last_heartbeat_at"] = event.get("resumed_at")
            state.pop("paused_at", None)
        elif kind == "study_session_completed":
            state.update(event)
            state["status"] = "completed"
            state["intervals"] = event.get("intervals") or state["intervals"]
            state["active_interval_started_at"] = None
            state["duration_seconds"] = int(event.get("duration_seconds") or sum(
                max(0, int((_dt(i.get("ended_at")) - _dt(i.get("started_at"))).total_seconds()))
                for i in state["intervals"] if _dt(i.get("started_at")) and _dt(i.get("ended_at"))
            ))
    if state.get("status") != "completed":
        state["duration_seconds"] = sum(max(0, int(item.get("duration_seconds") or 0)) for item in state["intervals"])
    return state


def _active_session() -> dict[str, Any] | None:
    ids = []
    for event in reversed(ACTIVITY_LOG):
        if event.get("kind") == "study_session_started" and event.get("session_id") not in ids:
            ids.append(event.get("session_id"))
    for session_id in ids:
        state = _session_state(str(session_id))
        if state and state.get("status") in {"active", "paused"}:
            return state
    return None


def _pause_at(state: dict[str, Any], at: datetime, *, reason: str) -> dict[str, Any]:
    active_start = _dt(state.get("active_interval_started_at"))
    if not active_start:
        return state
    end = max(active_start, at)
    interval = {"started_at": _iso(active_start), "ended_at": _iso(end), "duration_seconds": max(0, int((end - active_start).total_seconds()))}
    record_activity(
        "study_session_paused", session_id=state["session_id"], event_id=str(uuid4()),
        ended_at=_iso(end), interval=interval, reason=reason,
    )
    return _session_state(state["session_id"]) or state


def _recover_stale(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("status") != "active":
        return state
    heartbeat = _dt(state.get("last_heartbeat_at")) or _dt(state.get("active_interval_started_at"))
    now = _utc_now()
    if heartbeat and now - heartbeat > STALE_AFTER:
        # Count only up to the last confirmed heartbeat; never count time after connectivity vanished.
        return _pause_at(state, heartbeat, reason="Automatically paused after missing timer heartbeat.")
    return state


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
    """Restore a persisted timer, safely pausing if its heartbeat has gone stale."""
    with ACTIVITY_LOCK:
        active = _active_session()
        if active:
            active = _recover_stale(active)
        return {"active": active}


@router.get("/study-sessions/history")
def study_session_history(start: str | None = Query(None), end: str | None = Query(None)):
    """Return finalized sessions and active/paused sessions whose intervals are persisted."""
    with ACTIVITY_LOCK:
        ids = list(dict.fromkeys(
            str(event.get("session_id")) for event in ACTIVITY_LOG
            if event.get("kind") == "study_session_started" and event.get("session_id")
        ))
        sessions = [_session_state(session_id) for session_id in ids]
    sessions = [session for session in sessions if session]
    def history_boundary(raw: str | None, *, inclusive_end: bool = False) -> datetime | None:
        if not raw:
            return None
        # Date-only filters mean local calendar days in the app's configured IST timezone.
        try:
            if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
                day = datetime.fromisoformat(raw).date()
                if inclusive_end:
                    day += timedelta(days=1)
                return datetime.combine(day, datetime.min.time(), tzinfo=STUDY_TZ).astimezone(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="History date filters must be valid ISO dates or datetimes.")
        parsed = _dt(raw)
        if parsed is None:
            raise HTTPException(status_code=400, detail="History date filters must be valid ISO dates or datetimes.")
        return parsed

    start_dt, end_dt = history_boundary(start), history_boundary(end, inclusive_end=True)
    if start_dt or end_dt:
        def matches(session: dict[str, Any]) -> bool:
            stamp = _dt(session.get("started_at"))
            return bool(stamp and (not start_dt or stamp >= start_dt) and (not end_dt or stamp < end_dt))
        sessions = [session for session in sessions if matches(session)]
    return {"sessions": sessions}


@router.post("/study-sessions/start")
def start_study_session(payload: StudySessionStart):
    """Start one persisted session; server timestamp is authoritative."""
    with ACTIVITY_LOCK:
        current = _active_session()
        if current:
            current = _recover_stale(current)
            if current.get("status") in {"active", "paused"}:
                return {"session": current, "already_active": True}
        now = _iso(_utc_now())
        session_id = str(uuid4())
        record_activity(
            "study_session_started", session_id=session_id, started_at=now,
            last_heartbeat_at=now, topic=payload.topic.strip() if payload.topic and payload.topic.strip() else None,
            revision_task_id=payload.revision_task_id, status="active", intervals=[],
        )
        return {"session": _session_state(session_id), "already_active": False}


@router.post("/study-sessions/heartbeat")
def heartbeat_study_session(payload: StudySessionAction):
    with ACTIVITY_LOCK:
        state = _session_state(payload.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Study session not found.")
        if state.get("status") != "active":
            raise HTTPException(status_code=409, detail="Only an active study session can send a heartbeat.")
        now = _iso(_utc_now())
        started = next(e for e in ACTIVITY_LOG if e.get("kind") == "study_session_started" and e.get("session_id") == payload.session_id)
        started["last_heartbeat_at"] = now
        _save_activity()
        return {"session": _session_state(payload.session_id), "server_time": now}


@router.post("/study-sessions/pause")
def pause_study_session(payload: StudySessionAction):
    with ACTIVITY_LOCK:
        state = _session_state(payload.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Study session not found.")
        if state.get("status") == "paused":
            return {"session": state, "already_paused": True}
        if state.get("status") != "active":
            raise HTTPException(status_code=409, detail="Only an active study session can be paused.")
        now = _utc_now()
        state = _pause_at(state, now, reason="Paused by learner.")
        return {"session": state, "already_paused": False}


@router.post("/study-sessions/resume")
def resume_study_session(payload: StudySessionAction):
    with ACTIVITY_LOCK:
        state = _session_state(payload.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Study session not found.")
        if state.get("status") == "active":
            return {"session": state, "already_active": True}
        if state.get("status") != "paused":
            raise HTTPException(status_code=409, detail="Only a paused study session can be resumed.")
        now = _iso(_utc_now())
        record_activity("study_session_resumed", session_id=payload.session_id, event_id=str(uuid4()), resumed_at=now)
        return {"session": _session_state(payload.session_id), "already_active": False}


@router.post("/study-sessions/complete")
def complete_study_session(payload: StudySessionAction):
    """Finalize once using persisted active intervals; paused time is excluded."""
    with ACTIVITY_LOCK:
        state = _session_state(payload.session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Study session not found.")
        if state.get("status") == "completed":
            return {"session": state, "already_completed": True}
        if state.get("status") not in {"active", "paused"}:
            raise HTTPException(status_code=409, detail="This study session cannot be completed.")
        intervals = list(state.get("intervals") or [])
        now = _utc_now()
        active_start = _dt(state.get("active_interval_started_at"))
        if active_start:
            end = max(active_start, now)
            intervals.append({"started_at": _iso(active_start), "ended_at": _iso(end), "duration_seconds": max(0, int((end - active_start).total_seconds()))})
        # Merge/cap intervals defensively to prevent malformed or overlapping intervals inflating totals.
        normalized = []
        for interval in sorted(intervals, key=lambda item: item.get("started_at") or ""):
            left, right = _dt(interval.get("started_at")), _dt(interval.get("ended_at"))
            if not left or not right or right <= left:
                continue
            if normalized and left < _dt(normalized[-1]["ended_at"]):
                left = _dt(normalized[-1]["ended_at"])
            if right > left:
                normalized.append({"started_at": _iso(left), "ended_at": _iso(right), "duration_seconds": int((right-left).total_seconds())})
        duration = sum(item["duration_seconds"] for item in normalized)
        completed_at = _iso(now)
        record_activity(
            "study_session_completed", session_id=payload.session_id, event_id=str(uuid4()),
            started_at=state.get("started_at"), ended_at=completed_at, completed_at=completed_at,
            intervals=normalized, duration_seconds=duration, topic=state.get("topic"),
            revision_task_id=state.get("revision_task_id"), status="completed",
        )
        return {"session": _session_state(payload.session_id), "already_completed": False}
