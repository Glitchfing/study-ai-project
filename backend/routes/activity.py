from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Optional

from activity import record_activity

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
    extra: dict[str, Any] = Field(default_factory=dict)


@router.post("")
def log_activity(event: ActivityEvent):
    payload = event.model_dump(exclude={"kind", "extra"}, exclude_none=True)
    payload.update(event.extra or {})
    entry = record_activity(event.kind, **payload)
    return {"ok": True, "event": entry}


@router.get("/recent")
def recent_activity():
    from activity import ACTIVITY_LOG

    return {"items": list(reversed(ACTIVITY_LOG[-20:]))}
