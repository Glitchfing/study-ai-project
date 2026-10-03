from fastembed import TextEmbedding


# ============================================================
# CONFIG
# ============================================================

EMBEDDING_MODEL = (
    "BAAI/bge-small-en-v1.5"
)


# ============================================================
# EMBEDDING MODEL
# ============================================================

_embedding_model = None


def get_embedding_model():
    """
    Lazily initialize the embedding model.

    The model is loaded only when embeddings
    are actually required.
    """

    global _embedding_model

    if _embedding_model is None:

        print(
            "Loading embedding model:"
        )

        print(
            f"  {EMBEDDING_MODEL}"
        )

        _embedding_model = (
            TextEmbedding(
                model_name=EMBEDDING_MODEL
            )
        )

        print(
            "Embedding model loaded."
        )

    return _embedding_model


# ============================================================
# EMBED DOCUMENT CHUNKS
# ============================================================

def embed_texts(
    texts: list[str],
):
    """
    Generate embeddings for multiple texts.
    """

    if not texts:

        return []

    model = (
        get_embedding_model()
    )

    embeddings = model.embed(
        texts
    )

    return [
        embedding.tolist()
        for embedding in embeddings
    ]


# ============================================================
# EMBED ONE QUERY
# ============================================================

def embed_query(
    query: str,
):
    """
    Generate one embedding for a search query.
    """

    embeddings = embed_texts(
        [query]
    )

    if not embeddings:

        return []

    return embeddings[0]