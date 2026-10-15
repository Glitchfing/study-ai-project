"""REST API for ranked recommendations and their persistent lifecycle."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from activity import record_activity
from recommendation_store import (
    list_recommendations,
    refresh_recommendations,
    update_recommendation_status,
)

router = APIRouter()


class StatusNote(BaseModel):
    note: str | None = Field(default=None, max_length=500)


def _refresh_active(limit: int = 3) -> list[dict]:
    rows = refresh_recommendations(limit=max(limit * 3, limit))
    active = [row for row in rows if row.get("status", "pending") in {"pending", "in_progress"}]
    return active[:limit]


@router.get("")
def get_recommendations(
    limit: int = Query(3, ge=1, le=20),
    include_history: bool = Query(False),
):
    """Return current ranked recommendations, refreshing from persisted quiz data."""
    _refresh_active(limit)
    return {
        "recommendations": list_recommendations(include_history=include_history, limit=500)[:limit],
        "model_version": "1.0",
    }


@router.post("/refresh")
def refresh_current_recommendations(limit: int = Query(3, ge=1, le=20)):
    rows = _refresh_active(limit)
    return {"recommendations": rows, "model_version": "1.0"}


def _set_status(recommendation_id: str, status: str, note: str | None = None):
    row = update_recommendation_status(recommendation_id, status)
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found. Refresh recommendations and try again.")
    record_activity(
        f"recommendation_{status}",
        recommendation_id=recommendation_id,
        topic=row.get("topic"),
        concept=row.get("concept"),
        extra_note=note,
    )
    return {"recommendation": row}


@router.post("/{recommendation_id}/start")
def start_recommendation(recommendation_id: str, body: StatusNote | None = None):
    return _set_status(recommendation_id, "in_progress", body.note if body else None)


@router.post("/{recommendation_id}/complete")
def complete_recommendation(recommendation_id: str, body: StatusNote | None = None):
    return _set_status(recommendation_id, "completed", body.note if body else None)


@router.post("/{recommendation_id}/dismiss")
def dismiss_recommendation(recommendation_id: str, body: StatusNote | None = None):
    return _set_status(recommendation_id, "dismissed", body.note if body else None)
