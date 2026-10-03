from __future__ import annotations

import os
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)


# ============================================================
# CONFIG
# ============================================================

QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://localhost:6333",
)

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION",
    "study_documents",
)

# BAAI/bge-small-en-v1.5 = 384 dimensions
VECTOR_SIZE = 384


# ============================================================
# CLIENT
# ============================================================

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Return the shared Qdrant client.
    """

    global _client

    if _client is None:
        _client = QdrantClient(
            url=QDRANT_URL
        )

    return _client


# ============================================================
# CONNECTION TEST
# ============================================================

def check_qdrant_connection() -> bool:
    """
    Check whether the Qdrant server is reachable.
    """

    try:
        client = get_qdrant_client()

        client.get_collections()

        return True

    except Exception as exc:

        print(
            f"Qdrant connection failed: {exc}"
        )

        return False


# ============================================================
# COLLECTION
# ============================================================

def ensure_collection() -> None:
    """
    Create the Qdrant collection if it does not exist.
    """

    client = get_qdrant_client()

    collections = client.get_collections()

    existing_names = {
        collection.name
        for collection in collections.collections
    }

    if COLLECTION_NAME in existing_names:
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )

    print(
        f"Created Qdrant collection: "
        f"{COLLECTION_NAME}"
    )


# ============================================================
# QDRANT POINT ID
# ============================================================

def create_qdrant_point_id(
    chunk_id: str,
) -> str:
    """
    Convert our application chunk ID into a valid
    deterministic UUID for Qdrant.

    Qdrant accepts unsigned integers or UUIDs.

    Example application ID:

        abc123_0

    becomes:

        deterministic UUID
    """

    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            chunk_id,
        )
    )


# ============================================================
# INSERT CHUNKS
# ============================================================
# ============================================================
# INSERT CHUNKS
# ============================================================

def upsert_chunks(
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
) -> int:
    """
    Store document chunks and embeddings in Qdrant.

    Each vector stores:

        - document information
        - page information
        - section / heading information
        - chunk position
        - chunk type
        - original text

    The application chunk_id is preserved in the payload.

    Qdrant receives a deterministic UUID as its point ID,
    allowing the same chunk to be safely upserted again.
    """

    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    if not chunks:
        return 0

    if len(chunks) != len(embeddings):
        raise ValueError(
            "Number of chunks does not match "
            "number of embeddings."
        )

    # ========================================================
    # QDRANT
    # ========================================================

    ensure_collection()

    client = get_qdrant_client()

    points: list[PointStruct] = []

    # ========================================================
    # BUILD POINTS
    # ========================================================

    for index, (chunk, embedding) in enumerate(
        zip(chunks, embeddings)
    ):

        # ----------------------------------------------------
        # Validate embedding
        # ----------------------------------------------------

        if not embedding:
            raise ValueError(
                f"Empty embedding for chunk "
                f"{chunk.get('chunk_id', index)}."
            )

        if len(embedding) != VECTOR_SIZE:
            raise ValueError(
                f"Invalid embedding dimension for chunk "
                f"{chunk.get('chunk_id', index)}: "
                f"{len(embedding)}. "
                f"Expected {VECTOR_SIZE}."
            )

        # ----------------------------------------------------
        # Required fields
        # ----------------------------------------------------

        chunk_id = chunk.get(
            "chunk_id"
        )

        document_id = chunk.get(
            "document_id"
        )

        filename = chunk.get(
            "filename",
            "",
        )

        page = chunk.get(
            "page"
        )

        chunk_index = chunk.get(
            "chunk_index"
        )

        page_chunk_index = chunk.get(
            "page_chunk_index"
        )

        text = str(
            chunk.get(
                "text",
                "",
            )
        ).strip()

        # ----------------------------------------------------
        # Validate required fields
        # ----------------------------------------------------

        if not chunk_id:
            raise ValueError(
                f"Chunk at index {index} "
                f"is missing chunk_id."
            )

        if not document_id:
            raise ValueError(
                f"Chunk {chunk_id} is missing "
                f"document_id."
            )

        if not text:
            raise ValueError(
                f"Chunk {chunk_id} contains "
                f"empty text."
            )

        if page is None:
            raise ValueError(
                f"Chunk {chunk_id} is missing "
                f"page number."
            )

        # ----------------------------------------------------
        # Semantic metadata
        # ----------------------------------------------------

        heading = chunk.get(
            "heading"
        )

        chunk_type = chunk.get(
            "chunk_type",
            "paragraph",
        )

        # Normalize chunk type.
        if not chunk_type:
            chunk_type = "paragraph"

        # ----------------------------------------------------
        # Create deterministic Qdrant UUID
        # ----------------------------------------------------

        qdrant_point_id = (
            create_qdrant_point_id(
                chunk_id
            )
        )

        # ----------------------------------------------------
        # Create Qdrant point
        # ----------------------------------------------------

        point = PointStruct(

            id=qdrant_point_id,

            vector=embedding,

            payload={

                # ==========================================
                # IDENTIFIERS
                # ==========================================

                "chunk_id": chunk_id,

                "document_id": document_id,

                # ==========================================
                # DOCUMENT METADATA
                # ==========================================

                "filename": filename,

                "page": page,

                # ==========================================
                # CHUNK POSITION
                # ==========================================

                "chunk_index": chunk_index,

                "page_chunk_index": (
                    page_chunk_index
                ),

                # ==========================================
                # SEMANTIC METADATA
                # ==========================================

                "heading": heading,

                "chunk_type": chunk_type,

                # ==========================================
                # CONTENT
                # ==========================================

                "text": text,
            },
        )

        points.append(
            point
        )

    # ========================================================
    # BATCH UPSERT
    # ========================================================

    if not points:
        return 0

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )

    return len(points)
# ============================================================
# SEARCH
# ============================================================

def search_chunks(
    query_embedding: list[float],
    limit: int = 5,
    document_id: str | None = None,
) -> list[dict]:
    """
    Search for semantically similar document chunks.

    Optional document_id restricts results to one document.

    Returns:

        score
        chunk_id
        document_id
        filename
        page
        chunk_index
        page_chunk_index
        heading
        chunk_type
        text
    """

    # --------------------------------------------------------
    # Validate query
    # --------------------------------------------------------

    if not query_embedding:
        return []

    if len(query_embedding) != VECTOR_SIZE:
        raise ValueError(
            f"Invalid query embedding dimension: "
            f"{len(query_embedding)}. "
            f"Expected {VECTOR_SIZE}."
        )

    if limit <= 0:
        return []

    # Prevent unnecessarily large retrievals.
    limit = min(limit, 50)

    # --------------------------------------------------------
    # Ensure collection
    # --------------------------------------------------------

    ensure_collection()

    client = get_qdrant_client()

    # --------------------------------------------------------
    # Optional document filter
    # --------------------------------------------------------

    query_filter = None

    if document_id:

        query_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(
                        value=document_id
                    ),
                )
            ]
        )

    # --------------------------------------------------------
    # Semantic search
    # --------------------------------------------------------

    results = client.query_points(

        collection_name=COLLECTION_NAME,

        query=query_embedding,

        query_filter=query_filter,

        limit=limit,

        with_payload=True,
    )

    # --------------------------------------------------------
    # Convert Qdrant results
    # --------------------------------------------------------

    matches = []

    for point in results.points:

        payload = (
            point.payload or {}
        )

        matches.append(
            {
                # ==========================================
                # SIMILARITY
                # ==========================================

                "score": float(
                    point.score
                ),

                # ==========================================
                # IDENTIFIERS
                # ==========================================

                "chunk_id": payload.get(
                    "chunk_id"
                ),

                "document_id": payload.get(
                    "document_id"
                ),

                # ==========================================
                # DOCUMENT
                # ==========================================

                "filename": payload.get(
                    "filename"
                ),

                "page": payload.get(
                    "page"
                ),

                # ==========================================
                # CHUNK POSITION
                # ==========================================

                "chunk_index": payload.get(
                    "chunk_index"
                ),

                "page_chunk_index": payload.get(
                    "page_chunk_index"
                ),

                # ==========================================
                # SEMANTIC METADATA
                # ==========================================

                "heading": payload.get(
                    "heading"
                ),

                "chunk_type": payload.get(
                    "chunk_type",
                    "paragraph",
                ),

                # ==========================================
                # CONTENT
                # ==========================================

                "text": payload.get(
                    "text",
                    "",
                ),
            }
        )

    return matches
# ============================================================
# DELETE DOCUMENT
# ============================================================

def delete_document(
    document_id: str,
) -> None:
    """
    Delete every chunk belonging to a document.
    """

    ensure_collection()

    client = get_qdrant_client()

    client.delete(

        collection_name=COLLECTION_NAME,

        points_selector=Filter(
            must=[
                FieldCondition(
                    key="document_id",

                    match=MatchValue(
                        value=document_id
                    ),
                )
            ]
        ),

        wait=True,
    )


# ============================================================
# COLLECTION INFO
# ============================================================

def get_collection_info() -> dict:
    """
    Return basic information about the vector collection.
    """

    ensure_collection()

    client = get_qdrant_client()

    info = client.get_collection(
        collection_name=COLLECTION_NAME
    )

    return {
        "collection": COLLECTION_NAME,

        "vectors_count": (
            info.points_count
        ),

        "vector_size": VECTOR_SIZE,

        "distance": "cosine",
    }