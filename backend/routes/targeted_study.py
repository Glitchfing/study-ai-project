from __future__ import annotations

import io
import re
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from activity import record_activity
from diagram_pipeline import (
    attach_diagrams_to_sections,
    extract_diagrams_from_pdf,
)
from document_extractor import (
    extract_pdf_content,
    combine_extracted_content,
)
from note_generation import (
    generate_targeted_note_package,
    _split_pages,
)
from note_store import (
    attach_session_to_note,
    register_generated_note,
)
from session_store import create_study_session
from services.document_asset_store import (
    get_document_assets,
    get_document_diagrams,
    list_all_document_assets,
    register_document_assets,
)
from services.targeted_retrieval_service import retrieve_targeted_chunks
from routes.upload import (
    extract_text,
    ingest_document_into_qdrant,
    EXTRACTION_CACHE,
    MAX_EXTRACTION_CACHE_ITEMS,
)

router = APIRouter()


# ============================================================
# REQUEST MODELS
# ============================================================

class TargetedRetrievalRequest(BaseModel):
    document_id: str = Field(..., description="Target document ID stored in Qdrant")
    query: str = Field(..., description="Topic prompt or query (e.g. 'Tokenization')")
    top_k: int = Field(default=12, ge=1, le=50)
    max_chunks: int = Field(default=18, ge=1, le=50)


class TargetedStudyRequest(BaseModel):
    document_id: str = Field(..., description="Target document ID stored in Qdrant")
    query: str = Field(..., description="Topic prompt or query (e.g. 'Tokenization')")
    top_k: int = Field(default=12, ge=1, le=50)
    max_chunks: int = Field(default=18, ge=1, le=50)
    note_depth: str = Field(default="deep")
    include_examples: bool = Field(default=True)
    include_diagrams: bool = Field(default=True)


# ============================================================
# ENDPOINT 1: RETRIEVAL ONLY (DIAGNOSTIC / INSPECTION)
# ============================================================

@router.post("/targeted-retrieval")
def targeted_retrieval(req: TargetedRetrievalRequest):
    """
    Retrieve only the relevant source chunks from Qdrant for a topic,
    returning structured chunks and metadata without calling the LLM.
    """
    if not req.document_id.strip():
        raise HTTPException(status_code=400, detail="Document ID is required.")
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Topic / query is required.")

    result = retrieve_targeted_chunks(
        document_id=req.document_id,
        query=req.query,
        top_k=req.top_k,
        max_chunks=req.max_chunks,
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    doc_info = get_document_assets(req.document_id)
    filename = doc_info.get("filename") if doc_info else "Uploaded Document"

    return {
        "mode": "targeted_retrieval",
        "document_id": req.document_id,
        "filename": filename,
        "query": req.query,
        "retrieved_chunks": result["retrieved_chunks"],
        "context_word_count": result["context_word_count"],
        "pages": result["pages"],
        "headings": result["headings"],
        "matches": result["matches"],
        "context": result["context"],
    }


# ============================================================
# ENDPOINT 2: TARGETED STUDY GENERATION (EXISTING INDEXED DOC)
# ============================================================

@router.post("/targeted")
def generate_targeted_study(req: TargetedStudyRequest):
    """
    Generate focused study notes and quiz for a specific topic from an
    indexed document without re-processing the entire book.
    """
    clean_doc_id = req.document_id.strip()
    clean_query = req.query.strip()

    if not clean_doc_id:
        raise HTTPException(status_code=400, detail="Document ID is required.")
    if not clean_query:
        raise HTTPException(status_code=400, detail="Topic prompt is required.")

    # 1. Retrieve relevant source chunks from Qdrant
    retrieval = retrieve_targeted_chunks(
        document_id=clean_doc_id,
        query=clean_query,
        top_k=req.top_k,
        max_chunks=req.max_chunks,
    )

    if retrieval.get("error"):
        raise HTTPException(status_code=400, detail=retrieval["error"])

    if not retrieval.get("matches"):
        raise HTTPException(
            status_code=404,
            detail=f"No relevant sections found in this document for '{clean_query}'.",
        )

    # 2. Get document asset info & diagrams for retrieved pages
    doc_assets = get_document_assets(clean_doc_id)
    filename = doc_assets.get("filename") if doc_assets else "Uploaded Document"
    relevant_diagrams = get_document_diagrams(clean_doc_id, pages=retrieval.get("pages"))

    source_metadata = {
        "document_id": clean_doc_id,
        "filename": filename,
        "pages": retrieval.get("pages", []),
        "headings": retrieval.get("headings", []),
        "retrieved_chunks": retrieval.get("retrieved_chunks", 0),
        "context_word_count": retrieval.get("context_word_count", 0),
    }

    preferences = {
        "note_depth": req.note_depth,
        "preferred_format": "cornell",
        "exam_focus": True,
        "include_examples": req.include_examples,
        "include_diagrams": req.include_diagrams,
    }

    # 3. Targeted note generation
    source_content = retrieval.get("source_text") or retrieval.get("context", "")
    notes = generate_targeted_note_package(
        context=source_content,
        topic=clean_query,
        source_metadata=source_metadata,
        preferences=preferences,
        extracted_diagrams=relevant_diagrams,
    )

    # 4. Attach diagrams
    notes = attach_diagrams_to_sections(notes, relevant_diagrams)
    questions = notes.get("questions", [])

    # 5. Store note & create session
    note_id = register_generated_note(notes, topic=clean_query)

    session = create_study_session(
        uploaded_files=[{
            "filename": filename,
            "size_kb": doc_assets.get("size_kb", 0) if doc_assets else 0,
            "diagram_count": len(relevant_diagrams),
        }],
        note_id=note_id,
        note_title=notes.get("document_title") or f"{clean_query} — Targeted Study",
        selected_note_format="cornell",
        generation_mode="targeted",
    )

    notes["session_id"] = session["id"]
    attach_session_to_note(note_id, session["id"])

    # 6. Record activity
    record_activity(
        "targeted_study_generated",
        filename=filename,
        topic=clean_query,
        note_id=note_id,
        session_id=session["id"],
        total_questions=len(questions),
        diagrams_count=len(relevant_diagrams),
        generation_mode="targeted",
        source_pages=retrieval.get("pages", []),
        retrieved_chunks=retrieval.get("retrieved_chunks", 0),
    )

    return {
        "mode": "targeted",
        "session_id": session["id"],
        "note_id": note_id,
        "topic": clean_query,
        "filename": filename,
        "document_id": clean_doc_id,
        "retrieval": {
            "pages": retrieval.get("pages", []),
            "headings": retrieval.get("headings", []),
            "retrieved_chunks": retrieval.get("retrieved_chunks", 0),
            "context_word_count": retrieval.get("context_word_count", 0),
        },
        "notes": notes,
        "diagrams": relevant_diagrams,
        "quiz": questions,
        "generation_mode": "targeted",
    }


# ============================================================
# ENDPOINT 3: UPLOAD + INDEX + TARGETED STUDY (ONE-SHOT)
# ============================================================

@router.post("/upload-and-target")
def upload_and_target_study(
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    query: str = Form(..., description="Target topic prompt (e.g. 'Tokenization')"),
    top_k: int = Form(default=12),
    max_chunks: int = Form(default=18),
):
    """
    Upload a book/document, extract & index it into Qdrant once, and immediately
    generate targeted notes exclusively for the requested topic.
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="Topic prompt is required.")

    selected_files = files or ([file] if file else [])
    if not selected_files:
        raise HTTPException(status_code=400, detail="No files supplied.")

    documents = []
    all_diagrams = []
    total_size = 0

    for index, upload in enumerate(selected_files, start=1):
        filename = upload.filename or f"document-{index}"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        contents = upload.file.read()
        total_size += len(contents)

        text = extract_text(contents, filename)

        temp_note_id = re.sub(r"[^A-Za-z0-9_-]+", "_", filename.rsplit(".", 1)[0])[:60]
        extracted_diagrams = (
            extract_diagrams_from_pdf(contents, f"{temp_note_id}_{index}")
            if ext == "pdf"
            else []
        )

        for diagram in extracted_diagrams:
            diagram["source_filename"] = filename
            diagram["source_index"] = index

        all_diagrams.extend(extracted_diagrams)

        documents.append({
            "filename": filename,
            "text": text,
            "size_kb": round(len(contents) / 1024, 1),
            "diagrams": extracted_diagrams,
        })

    # Ingest each document into Qdrant
    primary_doc_id = None
    for doc in documents:
        qdrant_res = ingest_document_into_qdrant(text=doc["text"], filename=doc["filename"])
        doc_id = qdrant_res.get("document_id")
        if doc_id:
            register_document_assets(
                document_id=doc_id,
                filename=doc["filename"],
                diagrams=doc.get("diagrams", []),
                page_count=len(_split_pages(doc["text"])),
                size_kb=doc.get("size_kb", 0),
            )
            if not primary_doc_id:
                primary_doc_id = doc_id

    if not primary_doc_id:
        raise HTTPException(status_code=500, detail="Failed to index document into vector database.")

    # Run targeted study generation
    study_req = TargetedStudyRequest(
        document_id=primary_doc_id,
        query=clean_query,
        top_k=top_k,
        max_chunks=max_chunks,
    )
    return generate_targeted_study(study_req)


# ============================================================
# ENDPOINT 4: LIST INDEXED DOCUMENTS AVAILABLE FOR STUDY
# ============================================================

@router.get("/documents")
def get_indexed_documents():
    """
    Return all documents currently indexed in Qdrant & document asset store.
    """
    return list_all_document_assets()
