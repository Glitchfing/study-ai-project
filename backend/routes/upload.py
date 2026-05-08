import io
import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from activity import record_activity
from diagram_pipeline import attach_diagrams_to_sections, extract_diagrams_from_pdf
from note_generation import generate_note_package
from note_store import register_generated_note

router = APIRouter()

try:
    import PyPDF2

    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document as DocxDoc

    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf" and HAS_PDF:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append(f"[[PAGE_{index}]]\n{page.extract_text() or ''}")
        return "\n\n".join(pages)

    if ext == "docx" and HAS_DOCX:
        doc = DocxDoc(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)

    if ext in ("txt", "md"):
        return file_bytes.decode("utf-8", errors="replace")

    return f"[Extracted text from {filename} - install PyPDF2/python-docx for real extraction]"

def infer_topic(filename: str, text: str) -> str | None:
    lowered = f"{filename} {text}".lower()
    if any(token in lowered for token in ["nlp", "bert", "token", "text", "language"]):
        return "nlp"
    if any(token in lowered for token in ["ml", "model", "tree", "forest", "regression", "classification"]):
        return "ml"
    if any(token in lowered for token in ["data structure", "linked list", "stack", "queue", "graph", "tree"]):
        return "ds"
    return None


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    """Accept PDF / DOCX / TXT / image, extract text, return notes + quiz."""
    allowed = {"pdf", "docx", "txt", "md", "ppt", "pptx", "png", "jpg", "jpeg"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type '.{ext}' not supported.")

    contents = await file.read()
    text = extract_text(contents, file.filename)
    topic = infer_topic(file.filename, text)
    temp_note_id = file.filename.rsplit(".", 1)[0].replace(" ", "_")
    extracted_diagrams = extract_diagrams_from_pdf(contents, temp_note_id) if ext == "pdf" else []

    notes = generate_note_package(
        text,
        file.filename,
        preferences={
            "note_depth": "deep",
            "preferred_format": "cornell",
            "exam_focus": True,
            "include_examples": True,
            "include_diagrams": True,
        },
        extracted_diagrams=extracted_diagrams,
    )
    notes = attach_diagrams_to_sections(notes, extracted_diagrams)
    questions = notes.get("questions", [])
    note_id = register_generated_note(notes, topic)

    record_activity(
        "upload_processed",
        filename=file.filename,
        size_kb=round(len(contents) / 1024, 1),
        topic=topic,
        note_id=note_id,
        total_questions=len(questions),
        diagrams_count=len(extracted_diagrams),
    )

    return {
        "note_id": note_id,
        "filename": file.filename,
        "size_kb": round(len(contents) / 1024, 1),
        "text_preview": re.sub(r"\[\[PAGE_\d+\]\]\s*", "", text)[:500],
        "notes": notes,
        "diagrams": extracted_diagrams,
        "quiz": questions,
        "pipeline_steps": ["upload", "extract", "clean", "understand", "transform", "enhance", "store", "done"],
    }
