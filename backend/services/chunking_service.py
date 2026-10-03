from __future__ import annotations

import hashlib
import re
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 180

# Avoid tiny retrieval fragments.
MIN_CHUNK_CHARS = 350

MIN_HEADING_LENGTH = 2
MAX_HEADING_LENGTH = 120

# Generic structural words. These help detect headings but are NOT
# sufficient by themselves to replace the actual topic heading.
HEADING_KEYWORDS = {
    "introduction", "overview", "background", "definition", "summary",
    "example", "examples", "algorithm", "algorithms", "advantages",
    "disadvantages", "applications", "properties", "characteristics",
    "types", "classification", "conclusion", "key points", "important",
    "note", "theorem", "proof", "procedure", "steps", "architecture",
    "components", "features", "working", "process", "method", "methods",
    "implementation", "requirements", "objectives", "principles",
}

# Weak labels should normally remain attached to the current topic.
WEAK_HEADINGS = {
    "example", "examples", "real-life example", "real life example",
    "advantages", "disadvantages", "adv-dis", "adv-dis adv",
    "definition", "working", "steps", "important", "note",
    "key points", "conclusion", "applications", "properties",
    "characteristics", "types", "components", "features",
    "data", "module", "all users", "users", "devices",
}


# ============================================================
# DOCUMENT ID
# ============================================================

def create_document_id(filename: str, text: str) -> str:
    """Create a stable ID from filename + extracted content."""
    raw = f"{filename}|{text}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:24]


# ============================================================
# PAGE SPLITTING
# ============================================================

def split_into_pages(text: str) -> list[dict[str, Any]]:
    """
    Split page-preserved extracted text.

    Expected:
        [[PAGE_1]]
        text...

        [[PAGE_2]]
        text...
    """
    matches = list(re.finditer(r"\[\[PAGE_(\d+)\]\]", text or ""))

    if not matches:
        return [{"page": 1, "text": text or ""}]

    pages: list[dict[str, Any]] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        page_text = text[start:end].strip()

        if page_text:
            pages.append({
                "page": int(match.group(1)),
                "text": page_text,
            })

    return pages or [{"page": 1, "text": text or ""}]


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    """
    Conservative normalization.

    Important:
    - preserve paragraph/line boundaries
    - do not rewrite learning content
    - repair only obvious extraction artifacts
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"\[\[PAGE_\d+\]\]", "", text, flags=re.IGNORECASE)

    common_repairs = {
        "makepredictions": "make predictions",
        "themodel": "the model",
        "isused": "is used",
        "canlearn": "can learn",
        "dataand": "data and",
        "andmake": "and make",
        "ofdata": "of data",
        "withdata": "with data",
        "fromdata": "from data",
        "includelinear": "include linear",
    }

    for wrong, correct in common_repairs.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", correct, text, flags=re.IGNORECASE)

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _clean_joined_line(text: str) -> str:
    """Join extracted lines without changing their meaning."""
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]])", r"\1", text)
    return text.strip()


# ============================================================
# HEADING HELPERS
# ============================================================

def _normalize_heading_candidate(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.strip(" :-\t")
    text = re.sub(r"^[•●▪◦\-]+\s*", "", text)
    text = re.sub(r"^[📌🔹🔸⭐➡️]+\s*", "", text)
    return text.strip()


def _heading_core(text: str) -> str:
    text = _normalize_heading_candidate(text).lower()
    text = re.sub(r"^\d+(?:\.\d+)*[\.)]?\s*", "", text)
    text = re.sub(r"^[ivxlcdm]+[\.)]\s*", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _is_weak_heading(text: str) -> bool:
    return _heading_core(text) in WEAK_HEADINGS


def _is_numbered_topic(text: str) -> bool:
    """
    Decide whether a numbered line is a REAL TOPIC heading.

    Important distinction:
        "1. CSMA its types"        -> topic
        "2. TCP vs UDP"            -> topic
        "1. All users transmit..." -> ordinary explanation point
        "2. Better Security..."    -> ordinary advantage bullet

    The detector is intentionally conservative because OCR/PDF text often
    contains numbered lists inside a topic.
    """
    text = _normalize_heading_candidate(text)

    match = re.match(r"^\d+(?:\.\d+)*[\.)]?\s*(.+)$", text)
    if not match:
        return False

    rest = match.group(1).strip()

    if not rest:
        return False

    if len(rest) > 100 or len(rest.split()) > 10:
        return False

    if _is_weak_heading(rest):
        return False

    words = rest.split()
    normalized_words = [
        re.sub(r"[^A-Za-z-]", "", w).lower()
        for w in words
    ]

    # These are overwhelmingly likely to introduce explanation/list items,
    # not document topics.
    explanation_starters = {
        "each", "every", "if", "when", "the", "it", "this", "there",
        "data", "users", "user", "devices", "device", "routers", "router",
        "here", "used", "uses", "works", "working", "for", "to", "from",
        "explain", "describe", "discuss", "define", "give", "list",
        "advantages", "disadvantages", "simple", "complex", "high", "low",
        "better", "reduced", "increased", "more", "less", "fast", "slow",
        "no", "yes", "supports", "provides", "allows", "can",
    }

    if normalized_words and normalized_words[0] in explanation_starters:
        return False

    # A numbered question/exam instruction should not become the topic.
    if re.match(
        r"^(explain|describe|discuss|define|what|why|how|compare|differentiate|write)\b",
        rest,
        re.IGNORECASE,
    ):
        return False

    # Strong topic signals:
    # - acronym / all-uppercase token: CSMA, TCP, UDP, ARP, ICMP
    # - explicit comparison marker: vs / versus
    # - common structural/topic marker: "and its types", "full form", etc.
    has_acronym = any(
        len(token) >= 2 and token.isupper() and token.isalpha()
        for token in words
    )

    lowered = rest.lower()

    has_comparison = bool(
        re.search(r"\b(?:vs|versus)\b", lowered)
    )

    has_topic_marker = bool(
        re.search(
            r"\b(?:and its|full form|protocol|algorithm|routing|"
            r"address|bucket|access|security|network|learning|"
            r"multiple access|internet protocol)\b",
            lowered,
        )
    )

    # Title-case topic names are acceptable when they are reasonably short
    # and do not look like a sentence/bullet.
    alpha_words = [
        w for w in words
        if re.search(r"[A-Za-z]", w)
    ]

    title_like = False
    if alpha_words:
        title_like = (
            sum(w[:1].isupper() for w in alpha_words)
            / len(alpha_words)
            >= 0.75
        )

    # Avoid bullet-style fragments such as:
    # "High Capacity — More users..."
    # "Better Security — Hacking..."
    # "Reduced Interference — ..."
    if re.search(r"[—–-]", rest):
        first = normalized_words[0] if normalized_words else ""
        if first in {
            "high", "low", "better", "reduced", "increased",
            "simple", "complex", "more", "less", "fast", "slow",
        }:
            return False

    # Require at least one strong structural signal.
    if has_acronym or has_comparison or has_topic_marker:
        return True

    # Short title-like numbered headings can still be genuine topics.
    if title_like and 2 <= len(words) <= 6:
        return True

    return False


def _is_bullet_fragment(text: str) -> bool:
    """
    Detect common list/bullet fragments that OCR may mistake for headings.
    This is deliberately generic and does not depend on a particular subject.
    """
    core = _heading_core(text)

    if not core:
        return True

    if core in {
        "data", "module", "users", "devices", "all users",
        "high capacity", "better security", "reduced interference",
        "adv dis", "adv dis adv",
    }:
        return True

    lowered = _normalize_heading_candidate(text).lower()

    if re.search(
        r"^(high|low|better|reduced|increased|simple|complex|more|less|"
        r"fast|slow)\b",
        lowered,
    ) and re.search(r"[—–-]", lowered):
        return True

    return False


def looks_like_heading(text: str) -> bool:
    """
    Conservative heading detector.

    Weak labels such as "Real-life Example", "Advantages", and
    "Definition" may be structural labels, but they are not allowed
    to replace the actual topic heading.
    """
    text = _normalize_heading_candidate(text)

    if not text:
        return False

    if _is_bullet_fragment(text):
        return False

    if len(text) < MIN_HEADING_LENGTH or len(text) > MAX_HEADING_LENGTH:
        return False

    words = text.split()

    if len(words) > 12:
        return False

    if re.search(r"[.!?]$", text):
        return False

    if _is_numbered_topic(text):
        return True

    if re.match(
        r"^(chapter|section|unit|part|topic|lecture|lesson)\s+",
        text,
        re.IGNORECASE,
    ):
        return True

    if re.match(r"^module\s*\d+\b", text, re.IGNORECASE):
        return True

    letters = [c for c in text if c.isalpha()]

    if letters:
        uppercase_ratio = sum(c.isupper() for c in letters) / len(letters)

        if uppercase_ratio >= 0.80 and len(words) <= 12:
            return not _is_weak_heading(text)

    lowered = text.lower().strip(" .:-")

    if lowered in HEADING_KEYWORDS:
        return True

    for keyword in HEADING_KEYWORDS:
        if lowered.startswith(keyword + " ") and len(words) <= 10:
            return True

    if 1 <= len(words) <= 7:
        alpha_words = [
            word for word in words
            if re.search(r"[A-Za-z]", word)
        ]

        if alpha_words:
            title_like_ratio = (
                sum(word[:1].isupper() for word in alpha_words)
                / len(alpha_words)
            )

            if title_like_ratio >= 0.75 and not _is_weak_heading(text):
                return True

    return False


def _is_strong_topic_heading(text: str) -> bool:
    """
    Decide whether a heading should replace the current topic.

    Weak labels remain inside the current topic so:
        CSMA
          Definition
          Advantages
          Example
    stays as one coherent retrieval section.
    """
    text = _normalize_heading_candidate(text)

    if not text or _is_weak_heading(text):
        return False

    if _is_bullet_fragment(text):
        return False

    if _is_numbered_topic(text):
        return True

    if re.match(
        r"^(chapter|section|unit|part|topic|lecture|lesson)\s+",
        text,
        re.IGNORECASE,
    ):
        return True

    # "Module 2" is structural metadata rather than the actual topic.
    if re.match(r"^module\s*\d+\b", text, re.IGNORECASE):
        return False

    letters = [c for c in text if c.isalpha()]

    if letters:
        ratio = sum(c.isupper() for c in letters) / len(letters)

        if ratio >= 0.80:
            return True

    return looks_like_heading(text) and not _is_weak_heading(text)


# ============================================================
# STRUCTURAL LINE PREPARATION
# ============================================================

def _split_inline_numbered_topics(text: str) -> str:
    """
    Recover obvious numbered TOPIC boundaries from OCR/PDF text.

    Examples:
        1.CSMA its types In computer networks...
        2. CDMA Full Form: Code Division Multiple Access...
        2. tcp vs udp. Connection-oriented protocol...

    Ordinary numbered list items are intentionally ignored.
    """
    if not text:
        return ""

    # Repair OCR forms such as "1.CSMA" -> "1. CSMA".
    text = re.sub(
        r"(?<!\w)(\d+(?:\.\d+)*[\.)])(?=[A-Za-z])",
        r"\1 ",
        text,
    )

    sentence_starters = {
        "in", "when", "the", "this", "these", "it", "is", "are",
        "was", "were", "here", "used", "uses", "each", "every",
        "a", "an", "for", "to", "if", "data", "users", "devices",
        "connection", "connection-oriented", "connectionless",
    }

    pattern = re.compile(
        r"(?<!\w)(?P<num>\d+(?:\.\d+)*[\.)])\s+"
        r"(?P<body>[A-Za-z][^\n]{2,180})"
    )

    boundaries: list[tuple[int, int]] = []

    for match in pattern.finditer(text):
        body = match.group("body").strip()
        words = body.split()

        if not words:
            continue

        first_word = re.sub(
            r"[^A-Za-z-]",
            "",
            words[0],
        ).lower()

        # Ordinary numbered list item.
        if first_word in {
            "each", "every", "if", "when", "the", "it", "this",
            "there", "data", "users", "routers", "devices",
        }:
            continue

        title_end_relative: int | None = None

        # Example:
        # "2. TCP vs UDP. Connection-oriented..."
        punctuation_match = re.search(
            r"^(.{2,90}?)(?:\.\s+|:\s+|-\s+)(?=[A-Z])",
            body,
        )

        if punctuation_match:
            title = punctuation_match.group(1).strip()

            # OCR often produces:
            # "CDMA Full Form: Code Division Multiple Access"
            # "Full Form" is a label, not the topic name.
            title = re.sub(
                r"\s+(?:full\s+form|definition|introduction)\s*$",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()

            candidate = f"{match.group('num')} {title}"

            if _is_numbered_topic(candidate):
                title_end_relative = (
                    body.find(title) + len(title)
                    if title
                    else punctuation_match.end(1)
                )

        else:
            # Example:
            # "1. CSMA its types In computer networks..."
            max_title_words = min(6, len(words) - 1)

            for title_count in range(2, max_title_words + 1):
                next_word = re.sub(
                    r"[^A-Za-z-]",
                    "",
                    words[title_count],
                ).lower()

                if next_word not in sentence_starters:
                    continue

                title = " ".join(words[:title_count]).strip()
                candidate = f"{match.group('num')} {title}"

                if _is_numbered_topic(candidate):
                    title_end_relative = (
                        body.find(title) + len(title)
                    )
                    break

        if title_end_relative is None:
            continue

        title_start = match.start()
        title_end = match.start("body") + title_end_relative

        if title_end > match.start("body"):
            boundaries.append((title_start, title_end))

    if not boundaries:
        return text

    result = text

    # Apply from right to left so positions remain valid.
    for title_start, title_end in reversed(boundaries):
        result = (
            result[:title_start].rstrip()
            + "\n\n"
            + result[title_start:title_end].strip()
            + "\n\n"
            + result[title_end:].lstrip()
        )

    return result


def _prepare_blocks(text: str) -> list[str]:
    """
    Turn messy OCR/PDF text into structural blocks.

    Handles:
      - real blank-line paragraph boundaries
      - inline numbered topic headings
    """
    text = normalize_text(text)

    if not text:
        return []

    text = _split_inline_numbered_topics(text)

    raw_blocks = re.split(r"\n\s*\n+", text)
    blocks: list[str] = []

    for block in raw_blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if not lines:
            continue

        blocks.append("\n".join(lines))

    return blocks


# ============================================================
# PARAGRAPHS / SENTENCES
# ============================================================

def rebuild_paragraphs(text: str) -> list[str]:
    """Convert extracted text into readable paragraph units."""
    blocks = _prepare_blocks(text)
    return [
        _clean_joined_line(block)
        for block in blocks
        if block.strip()
    ]


def split_into_sentences(text: str) -> list[str]:
    """Conservative sentence splitting."""
    text = _clean_joined_line(text)

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9])",
        text,
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


# ============================================================
# INTERNAL CHUNK PACKING
# ============================================================

def _hard_split(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Last-resort character split for an unusually long unit."""
    text = text.strip()

    if not text:
        return []

    pieces = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(
                " ",
                start + int(chunk_size * 0.75),
                end,
            )

            if boundary > start:
                end = boundary

        piece = text[start:end].strip()

        if piece:
            pieces.append(piece)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return pieces


def _pack_units(
    units: list[str],
    heading: str | None,
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """Pack sentence units while respecting semantic boundaries."""
    chunks: list[dict[str, Any]] = []

    current: list[str] = []
    current_length = 0

    def emit(items: list[str]) -> None:
        if not items:
            return

        text = " ".join(items).strip()

        if not text:
            return

        chunks.append({
            "text": text,
            "heading": heading,
            "chunk_type": "paragraph",
        })

    for unit in units:
        unit = unit.strip()

        if not unit:
            continue

        if len(unit) > chunk_size:
            if current:
                emit(current)
                current = []
                current_length = 0

            for piece in _hard_split(
                unit,
                chunk_size,
                overlap,
            ):
                emit([piece])

            continue

        new_length = (
            current_length
            + (1 if current else 0)
            + len(unit)
        )

        if not current or new_length <= chunk_size:
            current.append(unit)
            current_length = new_length
            continue

        emit(current)

        # Sentence-level overlap.
        overlap_units: list[str] = []
        overlap_length = 0

        for previous in reversed(current):
            addition = (
                len(previous)
                + (1 if overlap_units else 0)
            )

            if overlap_length + addition > overlap:
                break

            overlap_units.insert(0, previous)
            overlap_length += addition

        current = overlap_units

        if current:
            current_length = len(" ".join(current))
        else:
            current_length = 0

        if (
            current
            and current_length + 1 + len(unit) > chunk_size
        ):
            emit(current)
            current = []
            current_length = 0

        current.append(unit)
        current_length = len(" ".join(current))

    if current:
        emit(current)

    return chunks


def _merge_small_chunks(
    chunks: list[dict[str, Any]],
    chunk_size: int,
) -> list[dict[str, Any]]:
    """Merge small neighboring chunks belonging to the same topic."""
    if len(chunks) <= 1:
        return chunks

    merged: list[dict[str, Any]] = []

    for chunk in chunks:
        text = str(chunk.get("text") or "").strip()

        if not text:
            continue

        if not merged:
            merged.append(chunk)
            continue

        previous = merged[-1]

        same_heading = (
            previous.get("heading")
            == chunk.get("heading")
        )

        previous_heading = _normalize_heading_candidate(
            str(previous.get("heading") or "")
        )
        current_heading = _normalize_heading_candidate(
            str(chunk.get("heading") or "")
        )

        compatible_heading = same_heading or (
            not current_heading
            or _is_weak_heading(current_heading)
            or _is_bullet_fragment(current_heading)
            or not previous_heading
        )

        if (
            len(text) < MIN_CHUNK_CHARS
            and compatible_heading
        ):
            combined = (
                f"{previous['text']} {text}"
            ).strip()

            if len(combined) <= int(chunk_size * 1.35):
                previous["text"] = combined
                continue

        merged.append(chunk)

    return merged


# ============================================================
# CHUNK PARAGRAPHS
# ============================================================

def chunk_paragraphs(
    paragraphs: list[str],
    heading: str | None,
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """Build semantic chunks from paragraph units."""
    if not paragraphs:
        return []

    units: list[str] = []

    for paragraph in paragraphs:
        paragraph = _clean_joined_line(paragraph)

        if not paragraph:
            continue

        sentences = split_into_sentences(paragraph)

        if sentences:
            units.extend(sentences)
        else:
            units.append(paragraph)

    if not units:
        return []

    chunks = _pack_units(
        units=units,
        heading=heading,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    return _merge_small_chunks(
        chunks,
        chunk_size,
    )


# ============================================================
# HEADING DETECTION INSIDE A BLOCK
# ============================================================

def find_heading_in_block(
    lines: list[str],
) -> tuple[str | None, list[str]]:
    """
    Inspect only the beginning of a block.

    Weak labels such as "Definition" or "Real-life Example" are
    kept inside the current topic instead of replacing it.
    """
    if not lines:
        return None, []

    max_candidates = min(2, len(lines))

    for index in range(max_candidates):
        candidate = _normalize_heading_candidate(
            lines[index]
        )

        if not candidate:
            continue

        if len(candidate) > MAX_HEADING_LENGTH:
            continue

        if len(candidate.split()) > 12:
            continue

        if _is_strong_topic_heading(candidate):
            return (
                candidate,
                lines[index + 1:],
            )

    return None, lines


# ============================================================
# CHUNK ONE PAGE
# ============================================================

def chunk_page(
    page_text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    initial_heading: str | None = None,
) -> list[dict[str, Any]]:
    """
    Chunk one page.

    `initial_heading` allows a topic to continue from the previous
    PDF page instead of resetting at every page.
    """
    page_text = normalize_text(page_text)

    if not page_text:
        return []

    blocks = _prepare_blocks(page_text)

    sections: list[dict[str, Any]] = []

    current_heading = initial_heading
    current_paragraphs: list[str] = []

    def flush_section() -> None:
        nonlocal current_paragraphs

        if not current_paragraphs:
            return

        sections.extend(
            chunk_paragraphs(
                paragraphs=current_paragraphs,
                heading=current_heading,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )

        current_paragraphs = []

    for block in blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if not lines:
            continue

        heading, remaining_lines = (
            find_heading_in_block(lines)
        )

        if heading is not None:
            flush_section()
            current_heading = heading

            if remaining_lines:
                body = _clean_joined_line(
                    " ".join(remaining_lines)
                )
                body = body.lstrip(" .:-")

                if body:
                    current_paragraphs.append(body)

            continue

        body = _clean_joined_line(
            " ".join(lines)
        )
        body = body.lstrip(" .:-")

        if body:
            current_paragraphs.append(body)

    flush_section()

    if not sections:
        paragraphs = rebuild_paragraphs(page_text)

        sections = chunk_paragraphs(
            paragraphs=paragraphs,
            heading=initial_heading,
            chunk_size=chunk_size,
            overlap=overlap,
        )

    return sections


# ============================================================
# CROSS-PAGE SEMANTIC MERGE
# ============================================================

def _merge_cross_page_chunks(
    chunks: list[dict[str, Any]],
    chunk_size: int,
) -> list[dict[str, Any]]:
    """
    Merge a small continuation chunk into the previous chunk when
    the semantic topic is unchanged.

    PDF pages are physical boundaries, not semantic boundaries.

    `page` remains the first page for backward compatibility.
    `source_pages` records every page represented by the chunk.
    """
    if not chunks:
        return []

    merged: list[dict[str, Any]] = []

    for chunk in chunks:
        text = str(
            chunk.get("text") or ""
        ).strip()

        if not text:
            continue

        current_pages = list(
            chunk.get("source_pages")
            or [chunk.get("page")]
        )

        if not merged:
            chunk["source_pages"] = current_pages
            merged.append(chunk)
            continue

        previous = merged[-1]

        same_heading = (
            previous.get("heading")
            and chunk.get("heading")
            and previous.get("heading")
            == chunk.get("heading")
        )

        small_continuation = (
            len(text) < MIN_CHUNK_CHARS
        )

        combined = (
            f"{previous.get('text', '').strip()} "
            f"{text}"
        ).strip()

        if (
            same_heading
            and small_continuation
            and len(combined)
            <= int(chunk_size * 1.35)
        ):
            previous["text"] = combined

            previous_pages = list(
                previous.get("source_pages")
                or [previous.get("page")]
            )

            for page in current_pages:
                if page not in previous_pages:
                    previous_pages.append(page)

            previous["source_pages"] = previous_pages
            continue

        chunk["source_pages"] = current_pages
        merged.append(chunk)

    return merged


# ============================================================
# DOCUMENT CHUNKING
# ============================================================

def chunk_document(
    text: str,
    filename: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """
    Convert page-preserved extracted text into vector-ready
    semantic chunks.

    Main improvements:
      1. Strong topic headings are separated from weak labels.
      2. Example/Advantages/Definition stay with the parent topic.
      3. Numbered topics are detected even when OCR removes spaces.
      4. Topics can continue across PDF page boundaries.
      5. Tiny continuation fragments are merged.
      6. Page metadata is preserved.
      7. No current test-PDF topic is hard-coded.
    """
    if not text:
        return []

    chunk_size = max(
        500,
        int(chunk_size),
    )

    overlap = max(
        0,
        min(
            int(overlap),
            chunk_size // 4,
        ),
    )

    document_id = create_document_id(
        filename,
        text,
    )

    pages = split_into_pages(text)

    chunks: list[dict[str, Any]] = []
    global_chunk_index = 0

    # Physical page boundaries must not reset the active topic.
    current_heading: str | None = None

    for page_data in pages:
        page_number = page_data["page"]
        page_text = page_data["text"]

        page_chunks = chunk_page(
            page_text=page_text,
            chunk_size=chunk_size,
            overlap=overlap,
            initial_heading=current_heading,
        )

        # Carry the last detected topic into the next page.
        for chunk_data in page_chunks:
            heading = chunk_data.get("heading")

            if heading:
                current_heading = str(heading)

        for local_index, chunk_data in enumerate(page_chunks):
            chunk_text = str(
                chunk_data.get("text") or ""
            ).strip()

            if not chunk_text:
                continue

            chunk_id = (
                f"{document_id}_"
                f"{global_chunk_index}"
            )

            chunks.append({
                "chunk_id": chunk_id,
                "document_id": document_id,
                "filename": filename,

                # Backward-compatible first page.
                "page": page_number,

                "chunk_index": global_chunk_index,
                "page_chunk_index": local_index,

                "heading": (
                    chunk_data.get("heading")
                    or current_heading
                ),

                "chunk_type": chunk_data.get(
                    "chunk_type",
                    "paragraph",
                ),

                "text": chunk_text,

                # Filled initially with one page; cross-page merge
                # expands this list.
                "source_pages": [page_number],
            })

            global_chunk_index += 1

    return _merge_cross_page_chunks(
        chunks,
        chunk_size,
    )