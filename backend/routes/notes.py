from fastapi import APIRouter, HTTPException, Query

from activity import record_activity
from note_store import get_normalized_note, get_note_content, get_note_record, list_notes

router = APIRouter()


@router.get("")
def get_all_notes():
    """Return list of all saved notes (metadata only)."""
    return list_notes()


@router.get("/{note_id}")
def get_note(note_id: str, format: str = Query("cornell")):
    """Return a specific note in the requested format."""
    note = get_note_record(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    record_activity(
        "note_view",
        note_id=note_id,
        topic=(note.get("topic") or "").lower() or None,
        format=format,
        title=note.get("title"),
    )

    result = {
        "id": note["id"],
        "title": note["title"],
        "topic": note["topic"],
        "updated": note["updated"],
    }
    result["content"] = get_note_content(note_id, format)
    return result


@router.get("/{note_id}/normalized")
def get_note_normalized(note_id: str):
    note = get_note_record(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return get_normalized_note(note_id)
