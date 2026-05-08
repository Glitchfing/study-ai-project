from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ATTEMPTS_DB_PATH = DATA_DIR / "quiz_attempts.json"

QUIZ_ATTEMPTS: list[dict[str, Any]] = []


def _load_attempts() -> list[dict[str, Any]]:
    if not ATTEMPTS_DB_PATH.exists():
        return []
    try:
        data = json.loads(ATTEMPTS_DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save_attempts() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ATTEMPTS_DB_PATH.write_text(json.dumps(QUIZ_ATTEMPTS, indent=2), encoding="utf-8")


def save_quiz_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    attempt = {
        "id": str(uuid4()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "note_id": payload.get("note_id"),
        "note_title": payload.get("note_title"),
        "topic": payload.get("topic") or "all",
        "topic_label": payload.get("topic_label") or "Quiz",
        "score": int(payload.get("score") or 0),
        "total": int(payload.get("total") or 0),
        "correct": int(payload.get("correct") or 0),
        "responses": payload.get("responses") or [],
        "weak_topics": payload.get("weak_topics") or [],
        "question_types": payload.get("question_types") or {},
        "duration_seconds": int(payload.get("duration_seconds") or 0),
    }
    QUIZ_ATTEMPTS.append(attempt)
    _save_attempts()
    return attempt


def list_quiz_attempts(note_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    attempts = QUIZ_ATTEMPTS
    if note_id:
        attempts = [attempt for attempt in attempts if attempt.get("note_id") == note_id]
    return list(reversed(attempts[-limit:]))


QUIZ_ATTEMPTS.extend(_load_attempts())
