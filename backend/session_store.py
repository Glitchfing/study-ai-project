from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DB_PATH = DATA_DIR / "study_sessions.json"

STUDY_SESSIONS: dict[str, dict[str, Any]] = {}


def _load_sessions() -> dict[str, dict[str, Any]]:
    if not SESSIONS_DB_PATH.exists():
        return {}
    try:
        data = json.loads(SESSIONS_DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_sessions() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DB_PATH.write_text(json.dumps(STUDY_SESSIONS, indent=2), encoding="utf-8")


def create_study_session(
    *,
    uploaded_files: list[dict[str, Any]],
    note_id: str,
    note_title: str,
    selected_note_format: str = "cornell",
    generation_mode: str = "fallback",
) -> dict[str, Any]:
    session_id = str(uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    session = {
        "id": session_id,
        "created_at": now,
        "updated_at": now,
        "uploaded_files": uploaded_files,
        "note_id": note_id,
        "note_title": note_title,
        "selected_note_format": selected_note_format,
        "generation_mode": generation_mode,
        "quiz_attempt_ids": [],
        "dashboard_analytics": {
            "uploaded_files_count": len(uploaded_files),
            "quizzes_attempted": 0,
            "highest_score": 0,
            "average_score": 0,
            "emoji_performance_history": [],
        },
    }
    STUDY_SESSIONS[session_id] = session
    _save_sessions()
    return session


def get_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    return STUDY_SESSIONS.get(session_id)


def find_session_by_note_id(note_id: str | None) -> dict[str, Any] | None:
    if not note_id:
        return None
    for session in STUDY_SESSIONS.values():
        if session.get("note_id") == note_id:
            return session
    return None


def update_session_note_format(note_id: str | None, note_format: str) -> None:
    session = find_session_by_note_id(note_id)
    if not session:
        return
    session["selected_note_format"] = note_format
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_sessions()


def attach_quiz_attempt(note_id: str | None, attempt: dict[str, Any], performance: dict[str, Any]) -> None:
    session = find_session_by_note_id(note_id)
    if not session:
        return
    analytics = session.setdefault("dashboard_analytics", {})
    history = analytics.setdefault("emoji_performance_history", [])
    history.append(
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
    session.setdefault("quiz_attempt_ids", []).append(attempt.get("id"))
    percentages = [int(item.get("percentage", 0)) for item in history]
    analytics["quizzes_attempted"] = len(history)
    analytics["highest_score"] = max(percentages) if percentages else 0
    analytics["average_score"] = round(sum(percentages) / len(percentages), 1) if percentages else 0
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_sessions()


def list_sessions() -> list[dict[str, Any]]:
    return list(STUDY_SESSIONS.values())


STUDY_SESSIONS.update(_load_sessions())
