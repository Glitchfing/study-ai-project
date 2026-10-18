from __future__ import annotations

import re
from typing import Any

from services.embedding_service import embed_query
from services.vector_store import search_chunks


def _normalize_text(value: Any) -> str:
    """Clean and normalize user queries, headings, and metadata strings."""
    if not value:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "into", "is", "it", "of", "on", "or", "the", "their",
    "this", "to", "using", "what", "when", "where", "which", "with",
    "cloud", "computing", "impact", "study", "targeted", "topic",
}


def _topic_terms(query: str) -> set[str]:
    """Return meaningful terms for a lightweight lexical relevance check."""
    return {
        token
        for token in re.findall(r"[a-z0-9+#-]{3,}", query.casefold())
        if token not in _STOPWORDS
    }


def _lexical_relevance(query: str, match: dict[str, Any]) -> float:
    """Supplement embedding similarity with evidence in chunk headings and text."""
    terms = _topic_terms(query)
    if not terms:
        return 1.0

    heading = _normalize_text(match.get("heading")).casefold()
    text = _normalize_text(match.get("text")).casefold()
    combined = f"{heading} {text}"
    matched = sum(
        1 for term in terms
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", combined)
    )
    if not matched:
        return 0.0

    heading_hits = sum(
        1 for term in terms
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", heading)
    )
    return min(1.0, (matched / len(terms)) * 0.75 + (0.25 if heading_hits else 0.0))


def _deduplicate_by_text(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove identical or near-identical chunks, preserving the higher-ranked result."""
    best: list[dict[str, Any]] = []
    for match in matches:
        text = re.sub(r"\W+", " ", str(match.get("text") or "").casefold()).strip()
        if not text:
            continue
        words = set(text.split())
        duplicate_index = None
        for index, previous in enumerate(best):
            prior_text = re.sub(r"\W+", " ", str(previous.get("text") or "").casefold()).strip()
            if text == prior_text:
                duplicate_index = index
                break
            prior_words = set(prior_text.split())
            if len(words) >= 8 and len(prior_words) >= 8:
                overlap = len(words & prior_words) / max(1, min(len(words), len(prior_words)))
                if overlap >= 0.92:
                    duplicate_index = index
                    break
        if duplicate_index is None:
            best.append(match)
        elif float(match.get("score") or 0.0) > float(best[duplicate_index].get("score") or 0.0):
            best[duplicate_index] = match
    return best


def _is_table_of_contents_chunk(match: dict[str, Any]) -> bool:
    """
    Detect if a chunk is merely a table of contents or index listing
    rather than substantive educational content.
    """
    heading = str(match.get("heading") or "").lower()
    text = str(match.get("text") or "")

    if any(toc_keyword in heading for toc_keyword in ["contents", "table of contents", "index"]):
        return True

    # Check for dotted chapter listings (e.g. "1.1 Introduction ... 5\n1.2 Overview ... 12")
    dot_leaders = len(re.findall(r"\.{3,}\s*\d+", text))
    if dot_leaders >= 3:
        return True

    # Check for index patterns (e.g. "Chapter 1 ... 1\nChapter 2 ... 15")
    chapter_rows = len(re.findall(r"(?:chapter|section|module|\d+\.\d+)\s+[^.\n]+\s+\d{1,4}", text, re.I))
    if chapter_rows >= 4:
        return True

    return False


def _deduplicate_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate chunks returned by vector search based on chunk_id or identical text,
    retaining the instance with the highest similarity score.
    """
    best_by_id: dict[str, dict[str, Any]] = {}

    for match in matches:
        chunk_id = match.get("chunk_id")
        if not chunk_id:
            text_hash = str(hash(match.get("text", "")))
            chunk_id = f"fallback_{match.get('page')}_{text_hash}"

        current_best = best_by_id.get(chunk_id)
        if current_best is None or match.get("score", 0.0) > current_best.get("score", 0.0):
            best_by_id[chunk_id] = match

    deduped = list(best_by_id.values())
    deduped.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return deduped


def _sort_for_reading(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Reorder semantically selected chunks into logical document reading order.
    Orders primarily by page number, then by chunk_index / page_chunk_index.
    """
    def sort_key(item: dict[str, Any]):
        page = item.get("page")
        if page is None or not isinstance(page, (int, float)):
            page = 999999
        chunk_index = item.get("chunk_index")
        if chunk_index is None or not isinstance(chunk_index, (int, float)):
            chunk_index = 999999
        page_chunk_index = item.get("page_chunk_index")
        if page_chunk_index is None or not isinstance(page_chunk_index, (int, float)):
            page_chunk_index = 999999
        return (int(page), int(chunk_index), int(page_chunk_index))

    return sorted(matches, key=sort_key)


def build_targeted_source_text(matches: list[dict[str, Any]]) -> str:
    """
    Reconstruct clean, page-preserved source text from retrieved chunks with [[PAGE_X]] markers.
    This allows semantic_section_builder and educational_note_generator to parse and synthesize
    learning sections with the full depth and quality of the standard note generation pipeline.
    """
    if not matches:
        return ""

    pages_dict: dict[int, list[str]] = {}
    for match in matches:
        page = match.get("page", 1)
        if page is None or not isinstance(page, int):
            try:
                page = int(page)
            except (ValueError, TypeError):
                page = 1

        raw_chunk_text = str(match.get("text", "")).strip()
        # Clean any accidental source tags
        clean_chunk = re.sub(r"\[SOURCE\s+\d+[^\]]*\]", "", raw_chunk_text).strip()
        if clean_chunk:
            heading = _normalize_text(match.get("heading"))
            if heading and not clean_chunk.lower().startswith(heading.lower()):
                clean_chunk = f"{heading}\n{clean_chunk}"
            pages_dict.setdefault(page, []).append(clean_chunk)

    parts = []
    for page_num in sorted(pages_dict.keys()):
        page_body = "\n\n".join(pages_dict[page_num])
        parts.append(f"[[PAGE_{page_num}]]\n{page_body}")

    return "\n\n".join(parts)


def _build_targeted_context(matches: list[dict[str, Any]]) -> str:
    """
    Format retrieved chunks for user inspection without polluting source text.
    """
    if not matches:
        return ""

    blocks = []
    for index, match in enumerate(matches, start=1):
        filename = match.get("filename") or "Document"
        page = match.get("page")
        page_str = f"Page {page}" if page is not None else "Page Unknown"
        heading = _normalize_text(match.get("heading"))
        heading_str = f" | Heading: {heading}" if heading else ""
        score = match.get("score", 0.0)
        raw_text = str(match.get("text", "")).strip()
        clean_text = re.sub(r"\[SOURCE\s+\d+[^\]]*\]", "", raw_text).strip()

        block_header = f"[SOURCE {index} | {filename} | {page_str}{heading_str} | Relevance: {score:.4f}]"
        blocks.append(f"{block_header}\n{clean_text}")

    return "\n\n".join(blocks)


def retrieve_targeted_chunks(
    *,
    document_id: str,
    query: str,
    top_k: int = 12,
    max_chunks: int = 18,
) -> dict[str, Any]:
    """
    Retrieve source chunks from Qdrant strictly filtered by document_id and ranked
    by semantic relevance to the user's requested topic/query.
    """
    clean_doc_id = _normalize_text(document_id)
    clean_query = _normalize_text(query)

    if not clean_doc_id:
        return {
            "document_id": "",
            "query": clean_query,
            "matches": [],
            "pages": [],
            "headings": [],
            "context": "",
            "source_text": "",
            "retrieved_chunks": 0,
            "context_word_count": 0,
            "error": "Missing document_id.",
        }

    if not clean_query:
        return {
            "document_id": clean_doc_id,
            "query": "",
            "matches": [],
            "pages": [],
            "headings": [],
            "context": "",
            "source_text": "",
            "retrieved_chunks": 0,
            "context_word_count": 0,
            "error": "Missing topic query.",
        }

    # Step 1 — Embed query
    query_embedding = embed_query(clean_query)
    if not query_embedding:
        return {
            "document_id": clean_doc_id,
            "query": clean_query,
            "matches": [],
            "pages": [],
            "headings": [],
            "context": "",
            "source_text": "",
            "retrieved_chunks": 0,
            "context_word_count": 0,
            "error": "Failed to generate query embedding.",
        }

    # Step 2 — Search Qdrant filtered by document_id
    limit = max(top_k * 2, max_chunks * 2)
    raw_matches = search_chunks(
        query_embedding=query_embedding,
        limit=limit,
        document_id=clean_doc_id,
    )

    # Step 3 — Deduplicate by stable chunk ID, then remove overlapping source text.
    deduped_matches = _deduplicate_matches(raw_matches)
    deduped_matches = _deduplicate_by_text(deduped_matches)

    # Step 4 — Remove navigation/index chunks when substantive content exists.
    content_matches = [m for m in deduped_matches if not _is_table_of_contents_chunk(m)]
    candidates = content_matches if content_matches else deduped_matches

    # Step 5 — Re-rank with topic-term evidence plus vector similarity.
    # Keep semantic recall, but reduce unrelated generic sections.
    for match in candidates:
        vector_score = float(match.get("score") or 0.0)
        lexical_score = _lexical_relevance(clean_query, match)
        match["lexical_relevance"] = round(lexical_score, 4)
        match["vector_score"] = round(vector_score, 4)
        match["score"] = round((0.72 * vector_score) + (0.28 * lexical_score), 6)

    candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)

    # If topic evidence exists, exclude candidates with no topical term matches.
    # Otherwise preserve semantic candidates for paraphrased or broad queries.
    if _topic_terms(clean_query):
        with_topic_evidence = [m for m in candidates if m.get("lexical_relevance", 0.0) > 0]
        if with_topic_evidence:
            candidates = with_topic_evidence

    # Step 6 — Select relevant chunks, then restore source order.
    selected_matches = candidates[:max_chunks]

    if not selected_matches:
        return {
            "document_id": clean_doc_id,
            "query": clean_query,
            "matches": [],
            "pages": [],
            "headings": [],
            "context": "",
            "source_text": "",
            "retrieved_chunks": 0,
            "context_word_count": 0,
        }

    # Step 7 — Restore document reading order after relevance ranking.
    ordered_matches = _sort_for_reading(selected_matches)

    # Step 8 — Extract metadata from selected source evidence only.
    pages = sorted(list({
        int(match["page"])
        for match in ordered_matches
        if match.get("page") is not None
    }))

    headings = []
    seen_headings = set()
    for match in ordered_matches:
        h = _normalize_text(match.get("heading"))
        if h and h.lower() not in seen_headings and not _is_table_of_contents_chunk(match):
            seen_headings.add(h.lower())
            headings.append(h)

    # Step 9 — Build clean page-preserved source text & inspection context.
    source_text = build_targeted_source_text(ordered_matches)
    context = _build_targeted_context(ordered_matches)
    context_word_count = len(re.findall(r"\b\w+\b", source_text))

    return {
        "document_id": clean_doc_id,
        "query": clean_query,
        "matches": ordered_matches,
        "pages": pages,
        "headings": headings,
        "context": context,
        "source_text": source_text,
        "retrieved_chunks": len(ordered_matches),
        "context_word_count": context_word_count,
    }
