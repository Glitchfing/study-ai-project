from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from activity import record_activity
from ai_generation import generate_structured_json
from services.embedding_service import embed_query
from services.vector_store import search_chunks


router = APIRouter()


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):
    message: str

    # Optional document identifier.
    #
    # When supplied, retrieval is restricted to that uploaded
    # document. This is important when multiple study files
    # exist in the same Qdrant collection.
    document_id: Optional[str] = None

    # Optional filename for UI/context purposes.
    filename: Optional[str] = None

    # Existing frontend compatibility.
    context: Optional[str] = None

    # Conversation history.
    history: Optional[list] = Field(
        default_factory=list
    )


# ============================================================
# RAG RESPONSE SCHEMA
# ============================================================

RAG_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {
            "type": "string"
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "chunk_id": {
                        "type": "string"
                    },
                    "page": {
                        "type": "integer"
                    },
                    "heading": {
                        "type": "string"
                    },
                    "filename": {
                        "type": "string"
                    }
                },
                "required": [
                    "chunk_id",
                    "page",
                    "heading",
                    "filename",
                ],
            },
        },
    },
    "required": [
        "answer",
        "sources",
    ],
}


# ============================================================
# RAG SETTINGS
# ============================================================

TOP_K = 6

# Maximum number of characters from one retrieved chunk
# included in the LLM context.
MAX_CHUNK_CHARS = 2200

# Maximum conversation history included in the prompt.
MAX_HISTORY_ITEMS = 6


# ============================================================
# TEXT HELPERS
# ============================================================

def _clean_text(
    value: object,
) -> str:
    """
    Normalize whitespace without changing the meaning of
    retrieved source content.
    """

    return " ".join(
        str(value or "").split()
    ).strip()


def _history_text(
    history: list,
) -> str:
    """
    Convert recent conversation history into compact text.
    """

    if not history:
        return ""

    recent = history[
        -MAX_HISTORY_ITEMS:
    ]

    lines = []

    for item in recent:

        if not isinstance(
            item,
            dict,
        ):
            continue

        role = (
            item.get("role")
            or item.get("sender")
            or "user"
        )

        content = (
            item.get("content")
            or item.get("message")
            or item.get("text")
            or ""
        )

        content = _clean_text(
            content
        )

        if not content:
            continue

        lines.append(
            f"{role}: {content}"
        )

    return "\n".join(lines)


# ============================================================
# BUILD RETRIEVAL CONTEXT
# ============================================================

def _build_retrieval_context(
    chunks: list[dict],
) -> tuple[str, list[dict]]:
    """
    Convert Qdrant results into an LLM-readable context block
    and a clean source list for the API response.
    """

    context_parts = []
    sources = []

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        text = _clean_text(
            chunk.get("text")
        )

        if not text:
            continue

        text = text[
            :MAX_CHUNK_CHARS
        ]

        page = chunk.get(
            "page"
        )

        heading = _clean_text(
            chunk.get("heading")
        )

        filename = _clean_text(
            chunk.get("filename")
        )

        chunk_id = _clean_text(
            chunk.get("chunk_id")
        )

        context_parts.append(
            "\n".join(
                [
                    f"[SOURCE {index}]",
                    f"Filename: {filename}",
                    f"Page: {page}",
                    f"Heading: {heading or 'General'}",
                    f"Content: {text}",
                ]
            )
        )

        # ----------------------------------------------------
        # Keep source metadata separate from source content.
        # The LLM is instructed to cite only retrieved sources.
        # ----------------------------------------------------

        if chunk_id:

            try:
                source_page = int(
                    page
                )
            except (
                TypeError,
                ValueError,
            ):
                source_page = 1

            sources.append(
                {
                    "chunk_id": chunk_id,
                    "page": source_page,
                    "heading": (
                        heading
                        or "General"
                    ),
                    "filename": (
                        filename
                        or "Unknown"
                    ),
                }
            )

    return (
        "\n\n".join(
            context_parts
        ),
        sources,
    )


# ============================================================
# RAG PROMPT
# ============================================================

def _build_system_prompt(
    document_scoped: bool,
) -> str:
    """
    System instructions for source-grounded study QA.
    """

    scope_instruction = (
        "The retrieved sources belong to the specific document selected by the student."
        if document_scoped
        else
        "The retrieved sources may come from the available study documents."
    )

    return f"""
You are the StudyAI learning assistant.

Your job is to answer the student's question using the
retrieved study material supplied in the user prompt.

{scope_instruction}

STRICT GROUNDING RULES:

1. Use the retrieved source material as the primary authority.
2. Do not invent facts that are not supported by the retrieved
   material.
3. If the retrieved material does not contain enough information
   to answer the question, clearly say that the uploaded study
   material does not provide enough information.
4. You may explain retrieved concepts in simpler language, but
   do not change their meaning.
5. Prefer educational explanations over extremely short answers.
6. For comparison questions, organize the answer clearly.
7. For process/workflow questions, explain the steps in order.
8. For definition questions, start with a clear definition.
9. Do not mention internal implementation details such as
   Qdrant, embeddings, vector databases, prompts, or retrieval.
10. The sources array must contain only sources that actually
    support the answer.
11. Do not fabricate page numbers, filenames, or source IDs.

The answer should be useful to a student studying for exams.
""".strip()


def _build_user_prompt(
    question: str,
    retrieval_context: str,
    history: list,
    extra_context: Optional[str],
) -> str:
    """
    Build the user-side RAG prompt.
    """

    history_block = _history_text(
        history
    )

    extra_context_block = (
        _clean_text(
            extra_context
        )
        if extra_context
        else ""
    )

    parts = [
        "STUDENT QUESTION:",
        question.strip(),
        "",
        "RETRIEVED STUDY MATERIAL:",
        retrieval_context,
    ]

    if history_block:

        parts.extend(
            [
                "",
                "RECENT CONVERSATION:",
                history_block,
            ]
        )

    if extra_context_block:

        parts.extend(
            [
                "",
                "ADDITIONAL STUDENT CONTEXT:",
                extra_context_block,
            ]
        )

    parts.extend(
        [
            "",
            "TASK:",
            "Answer the student's question using the retrieved study material.",
            "Return the answer and the supporting sources.",
        ]
    )

    return "\n".join(
        parts
    )


# ============================================================
# CHAT / RAG ENDPOINT
# ============================================================

@router.post("")
def chat(
    req: ChatRequest,
):
    """
    Answer a student's question using semantic retrieval
    followed by the existing StudyAI LLM layer.

    Flow:

        Question
           ↓
        BGE query embedding
           ↓
        Qdrant semantic search
           ↓
        Retrieved source chunks
           ↓
        Existing Groq → Gemini LLM layer
           ↓
        Grounded answer + sources
    """

    # ========================================================
    # VALIDATE QUESTION
    # ========================================================

    question = _clean_text(
        req.message
    )

    if not question:

        return {
            "response": (
                "Please enter a question "
                "about your study material."
            ),
            "model": "validation",
            "sources": [],
            "retrieval_count": 0,
        }

    # ========================================================
    # QUERY EMBEDDING
    # ========================================================

    query_embedding = embed_query(
        question
    )

    if not query_embedding:

        return {
            "response": (
                "I could not process the question "
                "for document retrieval."
            ),
            "model": "retrieval_error",
            "sources": [],
            "retrieval_count": 0,
        }

    # ========================================================
    # QDRANT SEARCH
    # ========================================================

    matches = search_chunks(
        query_embedding=query_embedding,
        limit=TOP_K,
        document_id=req.document_id,
    )

    # ========================================================
    # NO RETRIEVAL RESULTS
    # ========================================================

    if not matches:

        record_activity(
            "chat_message",
            message=question,
            topic=None,
            document_id=req.document_id,
            filename=req.filename,
            retrieval_count=0,
        )

        return {
            "response": (
                "I couldn't find relevant information "
                "in the available uploaded study material "
                "for that question."
            ),
            "model": "retrieval",
            "sources": [],
            "retrieval_count": 0,
            "document_id": req.document_id,
        }

    # ========================================================
    # BUILD CONTEXT
    # ========================================================

    retrieval_context, sources = (
        _build_retrieval_context(
            matches
        )
    )

    if not retrieval_context:

        return {
            "response": (
                "Relevant document sections were found, "
                "but they did not contain readable text."
            ),
            "model": "retrieval",
            "sources": sources,
            "retrieval_count": len(matches),
            "document_id": req.document_id,
        }

    # ========================================================
    # LLM GENERATION
    # ========================================================

    system_prompt = _build_system_prompt(
        document_scoped=bool(
            req.document_id
        )
    )

    user_prompt = _build_user_prompt(
        question=question,
        retrieval_context=retrieval_context,
        history=req.history or [],
        extra_context=req.context,
    )

    try:

        result = generate_structured_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name="rag_answer",
            schema=RAG_RESPONSE_SCHEMA,
            temperature=0.2,
            cache=True,
        )

    except Exception as exc:

        # ----------------------------------------------------
        # Retrieval itself succeeded.
        #
        # If the LLM provider is temporarily unavailable,
        # return the retrieved source excerpts instead of
        # pretending that generation succeeded.
        # ----------------------------------------------------

        fallback_sources = [
            {
                "chunk_id": chunk.get(
                    "chunk_id"
                ),
                "page": chunk.get(
                    "page"
                ),
                "heading": (
                    chunk.get("heading")
                    or "General"
                ),
                "filename": (
                    chunk.get("filename")
                    or "Unknown"
                ),
            }
            for chunk in matches
        ]

        fallback_lines = [
            "I found these relevant sections "
            "in your study material, but the "
            "AI answer generator is currently "
            "unavailable.",
            "",
        ]

        for index, chunk in enumerate(
            matches,
            start=1,
        ):

            text = _clean_text(
                chunk.get("text")
            )

            if not text:
                continue

            page = chunk.get(
                "page"
            )

            heading = (
                chunk.get("heading")
                or "General"
            )

            fallback_lines.append(
                f"[Source {index} | "
                f"Page {page} | "
                f"{heading}]"
            )

            fallback_lines.append(
                text[
                    :900
                ]
            )

            fallback_lines.append("")

        record_activity(
            "chat_message",
            message=question,
            topic=None,
            document_id=req.document_id,
            filename=req.filename,
            retrieval_count=len(matches),
            llm_error=str(exc),
        )

        return {
            "response": "\n".join(
                fallback_lines
            ).strip(),
            "model": "retrieval_fallback",
            "sources": fallback_sources,
            "retrieval_count": len(matches),
            "document_id": req.document_id,
            "llm_available": False,
        }

    # ========================================================
    # NORMALIZE LLM RESPONSE
    # ========================================================

    answer = _clean_text(
        result.get("answer")
    )

    if not answer:

        answer = (
            "I found relevant study material, "
            "but the generated answer was empty."
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We do not blindly trust the LLM-generated source list.
    # The actual source metadata comes from Qdrant.
    #
    # Therefore use the retrieved sources as the authoritative
    # source list.
    # --------------------------------------------------------

    final_sources = sources

    # ========================================================
    # ACTIVITY
    # ========================================================

    record_activity(
        "chat_message",
        message=question,
        topic=None,
        document_id=req.document_id,
        filename=req.filename,
        retrieval_count=len(matches),
        source_pages=[
            source["page"]
            for source in final_sources
        ],
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "response": answer,
        "model": "rag",
        "sources": final_sources,
        "retrieval_count": len(matches),
        "document_id": req.document_id,
        "llm_available": True,
    }