from fastapi import APIRouter, HTTPException, Query

from activity import record_activity
from note_store import get_normalized_note, get_note_content, get_note_record, list_notes
from session_store import update_session_note_format
from note_store import delete_generated_note

@router.delete("/{note_id}")
def delete_note(note_id: str):
    """Delete a saved generated note permanently."""
    try:
        deleted = delete_generated_note(note_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not delete note. Please try again.") from exc
    if not deleted:
        note = get_note_record(note_id)
        if note is not None and note.get("source") != "generated":
            raise HTTPException(status_code=403, detail="Example notes cannot be deleted.")
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": True, "id": note_id}



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
    update_session_note_format(note_id, format)

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
