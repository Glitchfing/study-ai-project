import io
import hashlib
import re
from copy import deepcopy

from fastapi import APIRouter, File, HTTPException, UploadFile

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
    generate_note_package,
    generate_session_note_package,
    _split_pages,
)
from note_store import (
    attach_session_to_note,
    register_generated_note,
)
from session_store import create_study_session

# ============================================================
# VECTOR DATABASE SERVICES
# ============================================================

from services.chunking_service import chunk_document
from services.embedding_service import embed_texts
from services.vector_store import (
    upsert_chunks,
    get_collection_info,
)
from services.document_asset_store import register_document_assets


router = APIRouter()


# ============================================================
# EXTRACTION CACHE
# ============================================================

EXTRACTION_CACHE: dict[str, dict] = {}

MAX_EXTRACTION_CACHE_ITEMS = 24


# ============================================================
# OPTIONAL DOCUMENT LIBRARIES
# ============================================================

try:
    from docx import Document as DocxDoc

    HAS_DOCX = True

except ImportError:
    HAS_DOCX = False


try:
    from pptx import Presentation

    HAS_PPTX = True

except ImportError:
    HAS_PPTX = False


# ============================================================
# DOCUMENT TEXT EXTRACTION
# ============================================================

def extract_text(
    file_bytes: bytes,
    filename: str,
) -> str:
    """
    Extract text from a supported document.

    PDF:
        Uses the canonical hybrid extractor from
        document_extractor.py.

    DOCX:
        Uses python-docx.

    PPT/PPTX:
        Uses python-pptx.

    TXT/MD:
        Uses UTF-8 decoding.
    """

    ext = filename.rsplit(".", 1)[-1].lower()

    # ========================================================
    # PDF
    # ========================================================

    if ext == "pdf":

        # ----------------------------------------------------
        # Use the canonical hybrid PDF extractor.
        #
        # It decides page-by-page whether to use:
        #
        #   Native PyMuPDF extraction
        #
        # or
        #
        #   Gemini Vision
        #
        # and returns page-preserved content.
        # ----------------------------------------------------

        results = extract_pdf_content(file_bytes)

        return combine_extracted_content(results)

    # ========================================================
    # DOCX
    # ========================================================

    if ext == "docx" and HAS_DOCX:

        doc = DocxDoc(
            io.BytesIO(file_bytes)
        )

        parts = []

        # ----------------------------------------------------
        # Paragraphs
        # ----------------------------------------------------

        for paragraph in doc.paragraphs:

            if paragraph.text.strip():

                parts.append(
                    paragraph.text.strip()
                )

        # ----------------------------------------------------
        # Tables
        # ----------------------------------------------------

        for table_index, table in enumerate(
            doc.tables,
            start=1,
        ):

            parts.append(
                f"Table {table_index}"
            )

            for row in table.rows:

                parts.append(
                    " | ".join(
                        cell.text.strip()
                        for cell in row.cells
                    )
                )

        return "\n".join(parts)

    # ========================================================
    # PPT / PPTX
    # ========================================================

    if ext in ("ppt", "pptx") and HAS_PPTX:

        presentation = Presentation(
            io.BytesIO(file_bytes)
        )

        slides = []

        for slide_index, slide in enumerate(
            presentation.slides,
            start=1,
        ):

            slide_parts = [
                f"[[PAGE_{slide_index}]]",
                f"Slide {slide_index}",
            ]

            for shape in slide.shapes:

                # ------------------------------------------------
                # Normal text
                # ------------------------------------------------

                if (
                    hasattr(shape, "text")
                    and shape.text
                    and shape.text.strip()
                ):

                    slide_parts.append(
                        shape.text.strip()
                    )

                # ------------------------------------------------
                # Tables
                # ------------------------------------------------

                if getattr(
                    shape,
                    "has_table",
                    False,
                ):

                    for row in shape.table.rows:

                        slide_parts.append(
                            " | ".join(
                                cell.text.strip()
                                for cell in row.cells
                            )
                        )

            slides.append(
                "\n".join(slide_parts)
            )

        return "\n\n".join(slides)

    # ========================================================
    # TXT / MARKDOWN
    # ========================================================

    if ext in ("txt", "md"):

        return file_bytes.decode(
            "utf-8",
            errors="replace",
        )

    # ========================================================
    # FALLBACK
    # ========================================================

    return (
        f"[Extracted text from {filename} - "
        f"install the required document extraction "
        f"library for this file type]"
    )


# ============================================================
# TOPIC INFERENCE
# ============================================================

def infer_topic(
    filename: str,
    text: str,
) -> str | None:

    lowered = (
        f"{filename} {text}"
    ).lower()

    # --------------------------------------------------------
    # NLP
    # --------------------------------------------------------

    if any(
        token in lowered
        for token in [
            "nlp",
            "bert",
            "token",
            "text",
            "language",
        ]
    ):

        return "nlp"

    # --------------------------------------------------------
    # Machine Learning
    # --------------------------------------------------------

    if any(
        token in lowered
        for token in [
            "ml",
            "model",
            "tree",
            "forest",
            "regression",
            "classification",
        ]
    ):

        return "ml"

    # --------------------------------------------------------
    # Data Structures
    # --------------------------------------------------------

    if any(
        token in lowered
        for token in [
            "data structure",
            "linked list",
            "stack",
            "queue",
            "graph",
            "tree",
        ]
    ):

        return "ds"

    return None


# ============================================================
# QDRANT INGESTION
# ============================================================

def ingest_document_into_qdrant(
    text: str,
    filename: str,
) -> dict:
    """
    Convert page-preserved source text into semantic chunks,
    generate embeddings, and store them in Qdrant.

    IMPORTANT:
        This stores the ORIGINAL extracted source material,
        not the generated study notes.

    This allows RAG to retrieve source-grounded content with
    reliable page and heading metadata.
    """

    # --------------------------------------------------------
    # Validate source
    # --------------------------------------------------------

    if not text or not text.strip():

        return {
            "stored": False,
            "filename": filename,
            "document_id": None,
            "chunks_created": 0,
            "vectors_stored": 0,
            "collection": None,
            "collection_vectors_count": 0,
            "error": "No source text available.",
        }

    # --------------------------------------------------------
    # Create semantic chunks
    # --------------------------------------------------------

    chunks = chunk_document(
        text=text,
        filename=filename,
    )

    if not chunks:

        return {
            "stored": False,
            "filename": filename,
            "document_id": None,
            "chunks_created": 0,
            "vectors_stored": 0,
            "collection": None,
            "collection_vectors_count": 0,
            "error": "No chunks were created from source text.",
        }

    # --------------------------------------------------------
    # Generate embeddings
    # --------------------------------------------------------

    chunk_texts = [
        chunk["text"]
        for chunk in chunks
    ]

    embeddings = embed_texts(
        chunk_texts
    )

    if not embeddings:

        return {
            "stored": False,
            "filename": filename,
            "document_id": chunks[0].get(
                "document_id"
            ),
            "chunks_created": len(chunks),
            "vectors_stored": 0,
            "collection": None,
            "collection_vectors_count": 0,
            "error": "No embeddings were generated.",
        }

    # --------------------------------------------------------
    # Store vectors in Qdrant
    # --------------------------------------------------------

    stored_count = upsert_chunks(
        chunks,
        embeddings,
    )

    # --------------------------------------------------------
    # Verify collection
    # --------------------------------------------------------

    collection_info = get_collection_info()

    document_id = chunks[0].get(
        "document_id"
    )

    return {
        "stored": (
            stored_count == len(chunks)
        ),
        "filename": filename,
        "document_id": document_id,
        "chunks_created": len(chunks),
        "embeddings_created": len(embeddings),
        "vectors_stored": stored_count,
        "collection": collection_info.get(
            "collection"
        ),
        "collection_vectors_count": collection_info.get(
            "vectors_count"
        ),
        "vector_size": collection_info.get(
            "vector_size"
        ),
        "distance": collection_info.get(
            "distance"
        ),
    }


# ============================================================
# UPLOAD ROUTE
# ============================================================

@router.post("")
def upload_file(
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
):
    """
    Accept one or many study files.

    Pipeline:

        Upload
          ↓
        Extraction
          ↓
        Source → Chunks → Embeddings → Qdrant
          ↓
        Document Intelligence
          ↓
        Note Generation
          ↓
        Diagram Connection
          ↓
        Note Store
          ↓
        Study Session
    """

    # ========================================================
    # SUPPORTED FILE TYPES
    # ========================================================

    allowed = {
        "pdf",
        "doc",
        "docx",
        "txt",
        "md",
        "ppt",
        "pptx",
        "png",
        "jpg",
        "jpeg",
    }

    # Support both:
    #
    #   files=[...]
    #
    # and the older:
    #
    #   file=...
    #

    selected_files = (
        files
        or ([file] if file else [])
    )

    if not selected_files:

        raise HTTPException(
            status_code=400,
            detail="No files supplied.",
        )

    # ========================================================
    # STORAGE FOR THIS UPLOAD
    # ========================================================

    documents = []

    all_diagrams = []

    total_size = 0

    # ========================================================
    # PROCESS EACH FILE
    # ========================================================

    for index, upload in enumerate(
        selected_files,
        start=1,
    ):

        filename = (
            upload.filename
            or f"document-{index}"
        )

        ext = (
            filename.rsplit(".", 1)[-1].lower()
            if "." in filename
            else ""
        )

        # ----------------------------------------------------
        # Validate extension
        # ----------------------------------------------------

        if ext not in allowed:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"File type '.{ext}' "
                    f"not supported."
                ),
            )

        # ----------------------------------------------------
        # Read uploaded file
        # ----------------------------------------------------

        contents = upload.file.read()

        total_size += len(contents)

        # ----------------------------------------------------
        # Cache key
        # ----------------------------------------------------

        cache_key = (
            f"{filename}:"
            f"{hashlib.sha256(contents).hexdigest()}"
        )

        cached = EXTRACTION_CACHE.get(
            cache_key
        )

        # ====================================================
        # USE CACHE
        # ====================================================

        if cached:

            text = cached["text"]

            extracted_diagrams = deepcopy(
                cached["diagrams"]
            )

        # ====================================================
        # FRESH EXTRACTION
        # ====================================================

        else:

            # ------------------------------------------------
            # Extract document content
            #
            # PDF → document_extractor.py
            # DOCX → python-docx
            # PPTX → python-pptx
            # TXT/MD → UTF-8
            # ------------------------------------------------

            text = extract_text(
                contents,
                filename,
            )

            # ------------------------------------------------
            # Diagram extraction
            #
            # This remains separate from text extraction.
            # ------------------------------------------------

            temp_note_id = re.sub(
                r"[^A-Za-z0-9_-]+",
                "_",
                filename.rsplit(
                    ".",
                    1,
                )[0],
            )[:60]

            extracted_diagrams = (
                extract_diagrams_from_pdf(
                    contents,
                    f"{temp_note_id}_{index}",
                )
                if ext == "pdf"
                else []
            )

            # ------------------------------------------------
            # Cache extraction result
            # ------------------------------------------------

            EXTRACTION_CACHE[cache_key] = {
                "text": text,
                "diagrams": deepcopy(
                    extracted_diagrams
                ),
            }

            # ------------------------------------------------
            # Limit cache size
            # ------------------------------------------------

            if (
                len(EXTRACTION_CACHE)
                > MAX_EXTRACTION_CACHE_ITEMS
            ):

                EXTRACTION_CACHE.pop(
                    next(
                        iter(
                            EXTRACTION_CACHE
                        )
                    )
                )

        # ====================================================
        # ADD SOURCE METADATA TO DIAGRAMS
        # ====================================================

        for diagram in extracted_diagrams:

            diagram["source_filename"] = filename

            diagram["source_index"] = index

        all_diagrams.extend(
            extracted_diagrams
        )

        # ====================================================
        # STORE DOCUMENT INFO
        # ====================================================

        documents.append(
            {
                "filename": filename,
                "text": text,
                "size_kb": round(
                    len(contents) / 1024,
                    1,
                ),
                "diagrams": extracted_diagrams,
            }
        )

    # ========================================================
    # VECTOR DATABASE INGESTION
    # ========================================================
    #
    # IMPORTANT:
    #
    # We use the ORIGINAL extracted source text.
    #
    # We do NOT embed the generated notes.
    #
    # This preserves:
    #
    #   document_id
    #   filename
    #   page
    #   heading
    #   chunk position
    #   source text
    #
    # for source-grounded RAG.
    # ========================================================

    qdrant_results = []

    for doc in documents:

        try:

            qdrant_result = ingest_document_into_qdrant(
                text=doc["text"],
                filename=doc["filename"],
            )

            if qdrant_result.get("document_id"):
                register_document_assets(
                    document_id=qdrant_result["document_id"],
                    filename=doc["filename"],
                    diagrams=doc.get("diagrams", []),
                    page_count=len(_split_pages(doc["text"])),
                    size_kb=doc.get("size_kb", 0),
                )

            qdrant_results.append(
                qdrant_result
            )

        except Exception as exc:

            # ------------------------------------------------
            # Do NOT silently hide Qdrant failures.
            #
            # Note generation can still proceed, but the API
            # response clearly reports that vector ingestion
            # failed.
            # ------------------------------------------------

            qdrant_results.append(
                {
                    "stored": False,
                    "filename": doc["filename"],
                    "document_id": None,
                    "chunks_created": 0,
                    "embeddings_created": 0,
                    "vectors_stored": 0,
                    "collection": None,
                    "collection_vectors_count": 0,
                    "error": str(exc),
                }
            )

    # ========================================================
    # COMBINE DOCUMENTS
    # ========================================================

    combined_text = "\n\n".join(
        doc["text"]
        for doc in documents
    )

    combined_name = " + ".join(
        doc["filename"]
        for doc in documents[:3]
    )

    # ========================================================
    # INFER TOPIC
    # ========================================================

    topic = infer_topic(
        combined_name,
        combined_text,
    )

    # ========================================================
    # GENERATE NOTES
    # ========================================================

    if len(documents) == 1:

        notes = generate_note_package(
            documents[0]["text"],
            documents[0]["filename"],
            preferences={
                "note_depth": "deep",
                "preferred_format": "cornell",
                "exam_focus": True,
                "include_examples": True,
                "include_diagrams": True,
            },
            extracted_diagrams=documents[0][
                "diagrams"
            ],
        )

    else:

        notes = generate_session_note_package(
            documents,
            preferences={
                "note_depth": "deep",
                "preferred_format": "cornell",
                "exam_focus": True,
                "include_examples": True,
                "include_diagrams": True,
            },
        )

    # ========================================================
    # ATTACH DIAGRAMS TO SECTIONS
    # ========================================================

    notes = attach_diagrams_to_sections(
        notes,
        all_diagrams,
    )

    # ========================================================
    # QUESTIONS
    # ========================================================

    questions = notes.get(
        "questions",
        [],
    )

    # ========================================================
    # STORE NOTE
    # ========================================================

    note_id = register_generated_note(
        notes,
        topic,
    )

    # ========================================================
    # UPLOADED FILE METADATA
    # ========================================================

    uploaded_files = [
        {
            "filename": doc["filename"],
            "size_kb": doc["size_kb"],
            "diagram_count": len(
                doc.get("diagrams") or []
            ),
        }
        for doc in documents
    ]

    # ========================================================
    # CREATE STUDY SESSION
    # ========================================================

    session = create_study_session(
        uploaded_files=uploaded_files,
        note_id=note_id,
        note_title=(
            notes.get("document_title")
            or combined_name
        ),
        selected_note_format="cornell",
        generation_mode=notes.get(
            "generation_mode",
            "fallback",
        ),
    )

    # ========================================================
    # ATTACH SESSION
    # ========================================================

    notes["session_id"] = session["id"]

    attach_session_to_note(
        note_id,
        session["id"],
    )

    # ========================================================
    # RECORD ACTIVITY
    # ========================================================

    record_activity(
        "upload_processed",
        filename=combined_name,
        file_count=len(documents),
        uploaded_files=[
            doc["filename"]
            for doc in documents
        ],
        size_kb=round(
            total_size / 1024,
            1,
        ),
        topic=topic,
        note_id=note_id,
        session_id=session["id"],
        total_questions=len(questions),
        diagrams_count=len(all_diagrams),
        generation_mode=notes.get(
            "generation_mode",
            "fallback",
        ),
        qdrant_stored=all(
            result.get("stored", False)
            for result in qdrant_results
        ),
        qdrant_vectors=sum(
            result.get(
                "vectors_stored",
                0,
            )
            for result in qdrant_results
        ),
    )

    # ========================================================
    # BUILD PREVIEW
    # ========================================================

    preview_parts = []

    for doc in documents:

        preview_text = re.sub(
            r"\[\[PAGE_\d+\]\]\s*",
            "",
            doc["text"],
        )[:280]

        preview_parts.append(
            f"{doc['filename']}\n"
            f"{preview_text}"
        )

    preview = "\n\n".join(
        preview_parts
    )

    # ========================================================
    # QDRANT SUMMARY
    # ========================================================

    qdrant_stored = (
        bool(qdrant_results)
        and all(
            result.get(
                "stored",
                False,
            )
            for result in qdrant_results
        )
    )

    total_chunks = sum(
        result.get(
            "chunks_created",
            0,
        )
        for result in qdrant_results
    )

    total_vectors = sum(
        result.get(
            "vectors_stored",
            0,
        )
        for result in qdrant_results
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "session_id": session["id"],
        "note_id": note_id,

        # ----------------------------------------------------
        # QDRANT STATUS
        # ----------------------------------------------------

        "qdrant": {
            "stored": qdrant_stored,
            "total_chunks": total_chunks,
            "total_vectors_stored": total_vectors,
            "documents": qdrant_results,
        },

        "filename": combined_name,

        "files": uploaded_files,

        "size_kb": round(
            total_size / 1024,
            1,
        ),

        "text_preview": preview[:900],

        "notes": notes,

        "diagrams": all_diagrams,

        "quiz": questions,

        "generation_mode": notes.get(
            "generation_mode",
            "fallback",
        ),

        # ----------------------------------------------------
        # PIPELINE STATUS
        # ----------------------------------------------------

        "pipeline_steps": [
            "upload",
            "extract_complete_text",
            "full_document_understanding",
            "document_intelligence_map",
            "source_chunking",
            "embedding_generation",
            "qdrant_storage",
            "semantic_educational_sections",
            "human_like_notes",
            "diagram_connection",
            "advanced_quiz",
            "note_store",
            "done",
        ],
    }