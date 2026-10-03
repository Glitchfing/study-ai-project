from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "each",
    "for",
    "from",
    "had",
    "has",
    "have",
    "having",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "not",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "those",
    "through",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}

SYNONYMS = {
    "use": {"application", "usage", "purpose", "function", "role"},
    "application": {"use", "usage", "purpose", "implementation"},
    "architecture": {"structure", "design", "layers", "framework"},
    "process": {"workflow", "flow", "pipeline", "steps", "procedure"},
    "workflow": {"process", "flow", "pipeline", "steps"},
    "advantage": {"benefit", "strength", "pros"},
    "disadvantage": {"limitation", "weakness", "cons"},
    "definition": {"meaning", "concept", "term"},
    "example": {"case", "scenario", "illustration"},
    "compare": {"contrast", "differentiate", "difference"},
    "component": {"module", "part", "unit", "element"},
}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+\-#.\s]", " ", text)
    return " ".join(text.split())


def tokenize(value: Any) -> list[str]:
    text = normalize_text(value)
    tokens = re.findall(r"[a-z][a-z0-9+\-#]{1,}", text)
    return [token for token in tokens if token not in STOPWORDS and len(token) > 2]


def expanded_tokens(value: Any) -> list[str]:
    output = []
    for token in tokenize(value):
        output.append(token)
        output.extend(SYNONYMS.get(token, set()))
    return output


def term_vector(value: Any, *, expand: bool = False) -> Counter[str]:
    return Counter(expanded_tokens(value) if expand else tokenize(value))


def cosine_similarity(left: Any, right: Any, *, expand: bool = False) -> float:
    left_vector = term_vector(left, expand=expand)
    right_vector = term_vector(right, expand=expand)
    if not left_vector or not right_vector:
        return 0.0
    shared = set(left_vector) & set(right_vector)
    numerator = sum(left_vector[token] * right_vector[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def keyword_overlap(left: Any, right: Any) -> float:
    left_terms = set(tokenize(left))
    right_terms = set(tokenize(right))
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / max(len(left_terms | right_terms), 1)


def top_keywords(value: Any, limit: int = 10) -> list[str]:
    counts = term_vector(value)
    return [token.replace("_", " ") for token, _ in counts.most_common(limit)]


def diverse_rank(
    query: str,
    candidates: Iterable[dict[str, Any]],
    *,
    text_key: str = "raw_text",
    limit: int = 4,
    min_similarity: float = 0.03,
) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: cosine_similarity(query, item.get(text_key, ""), expand=True),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    for candidate in ranked:
        score = cosine_similarity(query, candidate.get(text_key, ""), expand=True)
        if score < min_similarity:
            continue
        if any(cosine_similarity(candidate.get(text_key, ""), item.get(text_key, ""), expand=True) > 0.78 for item in selected):
            continue
        selected.append({**candidate, "retrieval_score": round(score, 4)})
        if len(selected) >= limit:
            break
    return selected


def extraction_quality_report(text: str, *, page_count: int = 1) -> dict[str, Any]:
    words = re.findall(r"\w+", text or "")
    alpha_chars = sum(1 for char in text if char.isalpha())
    total_chars = max(len(text), 1)
    replacement_chars = text.count("\ufffd") + text.count("�")
    word_count = len(words)
    words_per_page = round(word_count / max(page_count, 1), 1)
    alpha_ratio = round(alpha_chars / total_chars, 3)
    if word_count < max(35, page_count * 20):
        level = "poor"
    elif alpha_ratio < 0.45 or replacement_chars > max(6, word_count * 0.03):
        level = "noisy"
    else:
        level = "usable"
    return {
        "level": level,
        "word_count": word_count,
        "page_count": page_count,
        "words_per_page": words_per_page,
        "alpha_ratio": alpha_ratio,
        "replacement_characters": replacement_chars,
    }
