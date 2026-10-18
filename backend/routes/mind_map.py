from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.mind_map_service import generate_mind_map, get_saved_mind_map

router = APIRouter()


class GenerateMindMapRequest(BaseModel):
    topic: str | None = Field(default=None, max_length=180)


@router.get("/{note_id}/mind-map")
def get_mind_map(note_id: str, topic: str | None = Query(default=None, max_length=180)):
    try:
        result = get_saved_mind_map(note_id, topic)
    except KeyError:
        raise HTTPException(status_code=404, detail="Note not found.")
    if result is None:
        return {"note_id": note_id, "topic": topic, "exists": False, "mind_map": None}
    return {"note_id": note_id, "topic": topic, "exists": True, "mind_map": result}


@router.post("/{note_id}/mind-map/generate")
def create_mind_map(note_id: str, request: GenerateMindMapRequest):
    try:
        result = generate_mind_map(note_id, request.topic)
        return {"exists": True, "mind_map": result}
    except KeyError:
        raise HTTPException(status_code=404, detail="Note not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        # Do not leak provider credentials or internal tracebacks to clients.
        raise HTTPException(status_code=503, detail="Could not generate the mind map. Please retry.") from exc


@router.post("/{note_id}/mind-map/regenerate")
def regenerate_mind_map(note_id: str, request: GenerateMindMapRequest):
    try:
        result = generate_mind_map(note_id, request.topic, force=True)
        return {"exists": True, "mind_map": result}
    except KeyError:
        raise HTTPException(status_code=404, detail="Note not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not regenerate the mind map. The previous saved map, if any, was preserved.") from exc
