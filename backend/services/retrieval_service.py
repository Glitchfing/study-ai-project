from __future__ import annotations

from services.embedding_service import embed_query
from services.vector_store import search_chunks


# ============================================================
# CONFIG
# ============================================================

DEFAULT_TOP_K = 5


# ============================================================
# RETRIEVE RELEVANT CHUNKS
# ============================================================

def retrieve_relevant_chunks(
    question: str,
    document_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict]:
    """
    Retrieve the most semantically relevant chunks
    for a question.

    Flow:

        Question
            ↓
        Embedding
            ↓
        Qdrant similarity search
            ↓
        Relevant chunks
    """

    question = question.strip()

    if not question:
        return []

    # --------------------------------------------------------
    # Create query embedding
    # --------------------------------------------------------

    query_embedding = embed_query(
        question
    )

    if not query_embedding:
        return []

    # --------------------------------------------------------
    # Search Qdrant
    # --------------------------------------------------------

    results = search_chunks(
        query_embedding=query_embedding,
        limit=top_k,
        document_id=document_id,
    )

    return results


# ============================================================
# FORMAT RETRIEVED CONTEXT
# ============================================================

def build_retrieval_context(
    results: list[dict],
) -> str:
    """
    Convert retrieved chunks into context that can
    later be supplied to the AI generation layer.
    """

    if not results:
        return ""

    sections = []

    for index, result in enumerate(
        results,
        start=1,
    ):

        filename = result.get(
            "filename",
            "Unknown",
        )

        page = result.get(
            "page",
            "Unknown",
        )

        score = result.get(
            "score",
            0.0,
        )

        text = result.get(
            "text",
            "",
        ).strip()

        sections.append(
            f"[SOURCE {index}]\n"
            f"File: {filename}\n"
            f"Page: {page}\n"
            f"Relevance: {score:.4f}\n\n"
            f"{text}"
        )

    return "\n\n".join(
        sections
    )


# ============================================================
# HIGH-LEVEL RETRIEVAL
# ============================================================

def retrieve_context(
    question: str,
    document_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """
    Retrieve relevant chunks and return both the
    structured results and formatted context.
    """

    results = retrieve_relevant_chunks(
        question=question,
        document_id=document_id,
        top_k=top_k,
    )

    context = build_retrieval_context(
        results
    )

    return {
        "question": question,
        "results": results,
        "context": context,
        "result_count": len(results),
    }