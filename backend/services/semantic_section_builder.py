from __future__ import annotations

import re
from typing import Any

from semantic_utils import keyword_overlap, top_keywords


def _split_pages(text: str) -> list[dict[str, Any]]:
    matches = list(
        re.finditer(
            r"\[\[PAGE_(\d+)\]\]",
            text or "",
        )
    )

    if not matches:
        return [
            {
                "page_number": 1,
                "text": text or "",
            }
        ]

    pages = []

    for index, match in enumerate(matches):

        start = match.end()

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        page_text = text[start:end].strip()

        if page_text:
            pages.append(
                {
                    "page_number": int(match.group(1)),
                    "text": page_text,
                }
            )

    return pages or [
        {
            "page_number": 1,
            "text": text or "",
        }
    ]


def _paragraphs(text: str) -> list[str]:

    parts = [
        part.strip()
        for part in re.split(
            r"\n\s*\n+",
            text or "",
        )
        if part.strip()
    ]

    if len(parts) <= 1:

        parts = [
            line.strip()
            for line in (text or "").splitlines()
            if line.strip()
        ]

    return parts


def _looks_like_heading(
    value: str,
    previous_line: str = "",
) -> bool:
    """
    Generic heading detector used only for source segmentation.

    It intentionally accepts both major headings and child headings;
    document intelligence decides which ones are major.
    """
    raw = str(value or "").strip()
    if not raw or len(raw) > 100:
        return False

    if previous_line.strip() in {
        "•", "-", "●", "○", "▪", "◦", "*", "‣"
    }:
        return False

    cleaned = raw.strip(
        " :-\t•●▪◦–—"
    )

    if not cleaned:
        return False

    if raw.startswith("(") and raw.endswith(")"):
        return False

    # Explicit academic/document structure.
    if re.match(
        r"^(chapter|unit|module|topic|lecture|lesson|section|part)\b",
        cleaned,
        re.I,
    ):
        return True

    # Numbered or lettered child headings.
    if re.match(
        r"^(?:\d+(?:\.\d+)*|[A-Za-z])[\s.)]+",
        cleaned,
    ):
        return True

    # Structural child labels.
    lower = cleaned.casefold()
    structural_prefixes = (
        "step ",
        "significance of ",
        "applications of ",
        "types of ",
        "key components",
        "implementation",
        "key concepts",
        "common frameworks",
        "advantages",
        "disadvantages",
        "limitations",
        "procedure",
        "process",
    )
    if lower in {
        "simple",
        "type",
        "types",
        "working",
        "advantages",
        "disadvantages",
        "example",
        "examples",
        "notes",
        "details",
        "introduction",
        "overview",
        "information",
        "concept",
        "concepts",
        "key components",
        "implementation",
        "key concepts",
        "common frameworks",
        "limitations",
        "summary",
        "conclusion",
    }:
        return True

    if any(
        lower.startswith(prefix)
        for prefix in structural_prefixes
    ):
        return True

    if cleaned.endswith(
        (".", ",", ";", "?", "!")
    ):
        return False

    words = cleaned.split()

    if len(words) > 10:
        return False

    # Long lowercase prose fragments are not headings.
    capitalized = sum(
        1
        for word in words
        if word[:1].isupper()
    )
    if len(words) >= 6 and capitalized <= 2:
        return False

    title_like = (
        capitalized >= max(
            1,
            len(words) - 2,
        )
    )

    if title_like:
        return True

    # Mixed-case compact terms such as Word2Vec.
    if (
        len(words) == 1
        and re.match(
            r"^[A-Z][A-Za-z0-9+#.-]{2,}$",
            cleaned,
        )
        and (
            any(ch.islower() for ch in cleaned)
            or any(ch.isdigit() for ch in cleaned)
        )
    ):
        return True

    return False



def _topic_terms(
    topic: str,
    subtopics: list[str],
) -> list[str]:

    values = [topic]

    for item in subtopics:

        if (
            keyword_overlap(topic, item) > 0
            or item.lower() in topic.lower()
            or topic.lower() in item.lower()
        ):
            values.append(item)

    terms = []

    for value in values:

        terms.extend(
            top_keywords(
                value,
                limit=8,
            )
        )

        terms.extend(
            re.findall(
                r"[A-Za-z][A-Za-z0-9+#-]{2,}",
                value.lower(),
            )
        )

    return list(
        dict.fromkeys(
            terms
        )
    )


def _collect_blocks(
    text: str,
) -> list[dict[str, Any]]:
    """
    Line-aware source segmentation.

    PDF extraction frequently loses paragraph spacing. The old
    paragraph-only splitter could therefore miss headings such as
    "N-grams" or "Word2Vec" when they appeared inside one long
    extracted paragraph.

    This parser keeps the source order and starts a new block whenever
    a real heading is encountered.
    """
    blocks: list[dict[str, Any]] = []

    active_heading = ""
    active_source = ""

    buffer: list[str] = []
    buffer_page: int | None = None

    def flush() -> None:
        nonlocal buffer, buffer_page

        content = "\n".join(
            line
            for line in buffer
            if line.strip()
        ).strip()

        if content:
            blocks.append(
                {
                    "page_number": buffer_page or 1,
                    "heading": active_heading,
                    "source_filename": active_source,
                    "text": content,
                }
            )

        buffer = []
        buffer_page = None

    for page in _split_pages(text):
        page_number = int(
            page["page_number"]
        )

        raw_lines = (
            page["text"] or ""
        ).splitlines()

        for line_index, raw_line in enumerate(
            raw_lines
        ):
            line = raw_line.rstrip()

            if not line.strip():
                if buffer:
                    buffer.append("")
                continue

            source_match = re.match(
                r"^Source file:\s*(.+)$",
                line.strip(),
                re.I,
            )

            if source_match:
                flush()
                active_source = (
                    source_match.group(1).strip()
                )
                continue

            previous_line = (
                raw_lines[line_index - 1].strip()
                if line_index > 0
                else ""
            )

            if _looks_like_heading(
                line,
                previous_line,
            ):
                flush()
                active_heading = (
                    line.strip(
                        " :-\t•●▪◦–—"
                    )
                )
                buffer_page = page_number
                continue

            if buffer_page is None:
                buffer_page = page_number

            buffer.append(line)

        # Keep page boundaries explicit. Do not merge an entire
        # following page into a previous heading block when the page
        # has no text.
        if buffer:
            flush()

    return blocks



def _block_score(
    topic: str,
    block: dict[str, Any],
    topic_terms: list[str],
) -> float:

    context = (
        f"{block.get('heading', '')} "
        f"{block.get('text', '')}"
    )

    score = 0.0

    # Direct topic match is strongest.
    if topic.lower() in context.lower():
        score += 1.0

    # Compare topic terminology with the block.
    for term in topic_terms:

        if term.lower() in context.lower():
            score += 0.12

    # Semantic keyword overlap.
    score += keyword_overlap(
        topic,
        context,
    )

    return score


def merge_related_concepts(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    merged: list[dict[str, Any]] = []

    for section in sections:

        if (
            merged
            and section["title"].lower()
            == merged[-1]["title"].lower()
        ):

            merged[-1]["raw_text"] = (
                f"{merged[-1]['raw_text']}\n\n"
                f"{section['raw_text']}"
            ).strip()

            merged[-1]["page_numbers"] = sorted(
                set(
                    merged[-1]["page_numbers"]
                    + section["page_numbers"]
                )
            )

            merged[-1]["learning_objectives"] = list(
                dict.fromkeys(
                    merged[-1][
                        "learning_objectives"
                    ]
                    + section[
                        "learning_objectives"
                    ]
                )
            )

            continue

        merged.append(section)

    for index, section in enumerate(
        merged,
        start=1,
    ):

        section["section_id"] = (
            f"section-{index}"
        )

        section["order_index"] = (
            index - 1
        )

    return merged


def preserve_topic_flow(
    sections: list[dict[str, Any]],
    intelligence: dict[str, Any],
) -> list[dict[str, Any]]:

    order = {
        topic.lower(): index
        for index, topic in enumerate(
            intelligence.get(
                "revision_priority_order"
            )
            or []
        )
    }

    return sorted(
        sections,
        key=lambda item: (
            order.get(
                item["title"].lower(),
                item.get(
                    "order_index",
                    999,
                ),
            ),
            item.get(
                "order_index",
                999,
            ),
        ),
    )


def _clean_heading(value: str) -> str:
    """Normalize a heading before using it as a learning-section title."""
    value = re.sub(r"\s+", " ", (value or "").strip(" :-\t"))
    value = re.sub(r"^[•●▪◦\-–—]+\s*", "", value)
    return value.strip()


def _heading_quality(value: str) -> float:
    """
    Score whether a detected heading is useful as a real section.

    Short fragments such as "Simple", "Types", or a sentence copied
    from the source should not become standalone study sections.
    """
    value = _clean_heading(value)

    if not value or len(value) > 100:
        return 0.0

    words = value.split()

    # Reject obvious sentence fragments.
    if len(words) >= 7 and value.endswith((".", "?", "!")):
        return 0.0

    # Reject very short generic headings unless they have numbering.
    generic = {
        "simple",
        "types",
        "working",
        "advantages",
        "disadvantages",
        "example",
        "examples",
        "notes",
        "introduction",
        "conclusion",
    }

    if len(words) <= 1 and value.lower() in generic:
        return 0.0

    score = 1.0

    if re.match(
        r"^(chapter|unit|module|topic|lecture|lesson|section|part)\b",
        value,
        re.I,
    ):
        score += 2.0

    if re.match(r"^\d+(\.\d+)*\s+\S+", value):
        score += 1.5

    if len(words) <= 8:
        score += 0.5

    return score


def _build_heading_sections(
    blocks: list[dict[str, Any]],
    filename: str,
) -> list[dict[str, Any]]:
    """
    Build sections directly from the document's own headings.

    WHY THIS EXISTS:
    ----------------
    If document intelligence fails or produces unreliable topic names,
    forcing every paragraph into an LLM-generated topic can create
    nonsense sections such as:

        "Simple"
        "Types"
        "Here the device continuously listens..."

    For educational notes, the document's actual heading structure is
    safer than inventing topic boundaries.

    Small generic headings are kept inside the surrounding section
    rather than becoming independent sections.
    """

    sections = []
    current = None

    for block in blocks:
        heading = _clean_heading(
            block.get("heading") or ""
        )
        content = (block.get("text") or "").strip()

        if not content:
            continue

        heading_is_real = (
            _heading_quality(heading) >= 1.0
        )

        # A new meaningful heading starts a new section.
        if heading_is_real:
            # If the heading is only a generic one-word label,
            # keep it inside the current section.
            if (
                current is not None
                and len(heading.split()) <= 1
                and heading.lower()
                in {
                    "simple",
                    "types",
                    "working",
                    "advantages",
                    "disadvantages",
                    "example",
                    "examples",
                }
            ):
                current["raw_text"] = (
                    f"{current['raw_text']}\n\n"
                    f"{heading}\n{content}"
                ).strip()
                current["page_numbers"].append(
                    block["page_number"]
                )
                continue

            current = {
                "section_id": (
                    f"section-{len(sections) + 1}"
                ),
                "title": heading,
                "raw_text": content,
                "page_numbers": [
                    block["page_number"]
                ],
                "source_filename": (
                    block.get("source_filename")
                    or filename
                ),
                "concept_group": heading,
                "section_type": "concept",
                "learning_objectives": [
                    (
                        f"Explain {heading} "
                        "clearly in exam language."
                    ),
                    (
                        f"Connect {heading} "
                        "with related concepts and examples."
                    ),
                ],
                "related_topics": [],
                "concept_keywords": top_keywords(
                    f"{heading} {content}",
                    limit=12,
                ),
            }

            sections.append(current)
            continue

        # Content before the first usable heading:
        # keep it in a safe introductory section instead of
        # inventing a random topic.
        if current is None:
            current = {
                "section_id": "section-1",
                "title": (
                    filename
                    .rsplit(".", 1)[0]
                    .replace("_", " ")
                    .replace("-", " ")
                    .title()
                ),
                "raw_text": content,
                "page_numbers": [
                    block["page_number"]
                ],
                "source_filename": (
                    block.get("source_filename")
                    or filename
                ),
                "concept_group": "Introduction",
                "section_type": "concept",
                "learning_objectives": [
                    "Understand the main concepts in this material."
                ],
                "related_topics": [],
                "concept_keywords": top_keywords(
                    content,
                    limit=12,
                ),
            }
            sections.append(current)
        else:
            current["raw_text"] = (
                f"{current['raw_text']}\n\n{content}"
            ).strip()
            current["page_numbers"].append(
                block["page_number"]
            )

    # De-duplicate page numbers.
    for section in sections:
        section["page_numbers"] = sorted(
            set(section["page_numbers"])
        )

    return sections


def _intelligence_is_usable(
    topics: list[str],
    blocks: list[dict[str, Any]],
) -> bool:
    """
    Decide whether LLM document intelligence is safe enough
    to drive section construction.
    """
    if not topics:
        return False

    clean_topics = [
        _clean_heading(topic)
        for topic in topics
        if _clean_heading(topic)
    ]

    if not clean_topics:
        return False

    # Avoid treating sentence-like garbage as major topics.
    usable = [
        topic
        for topic in clean_topics
        if _heading_quality(topic) >= 1.0
    ]

    if not usable:
        return False

    # If there are many tiny/generic topics, the intelligence
    # is probably malformed.
    generic_count = sum(
        1
        for topic in usable
        if topic.lower()
        in {
            "simple",
            "types",
            "working",
            "advantages",
            "disadvantages",
            "module2",
        }
    )

    if generic_count >= max(
        2,
        len(usable) // 2,
    ):
        return False

    return True


def _heading_matches_topic(
    heading: str,
    topic: str,
) -> bool:
    """
    Match a source heading to a major topic without allowing broad
    substring matches such as:
        Bag of Words <- CBOW (Continuous Bag of Words)
    """
    h = re.sub(
        r"[^a-z0-9+#]+",
        " ",
        str(heading or "").casefold(),
    ).strip()
    t = re.sub(
        r"[^a-z0-9+#]+",
        " ",
        str(topic or "").casefold(),
    ).strip()

    if not h or not t:
        return False

    if h == t:
        return True

    h_tokens = set(h.split())
    t_tokens = set(t.split())

    if not h_tokens or not t_tokens:
        return False

    overlap = len(
        h_tokens.intersection(t_tokens)
    )

    # Permit an expanded heading only when it is a small expansion
    # of the topic itself.
    if (
        overlap == len(t_tokens)
        and len(h_tokens) <= len(t_tokens) + 2
    ):
        return True

    return False


def create_learning_sections(
    blocks: list[dict[str, Any]],
    intelligence: dict[str, Any],
    filename: str,
) -> list[dict[str, Any]]:
    """
    Build one coherent section per document-level major topic.

    The important improvement is PAGE-AWARE assignment:
      1. direct major-topic heading match
      2. subtopic -> parent-topic match from document intelligence
      3. unique page ownership
      4. keyword scoring as a final local fallback

    This prevents unrelated pages from being pulled into the wrong topic.
    """

    topics = list(
        dict.fromkeys(
            _clean_heading(topic)
            for topic in (
                intelligence.get("major_topics") or []
            )
            if _clean_heading(topic)
        )
    )

    if not topics:
        return _build_heading_sections(
            blocks,
            filename,
        )

    # ------------------------------------------------------------
    # Build page/subtopic evidence from the intelligence map.
    # ------------------------------------------------------------
    topic_details: dict[str, dict[str, Any]] = {}

    for item in intelligence.get("topics") or []:
        if not isinstance(item, dict):
            continue

        title = _clean_heading(
            str(item.get("title") or "")
        )

        if not title:
            continue

        topic_details[title] = item

    topic_pages: dict[str, set[int]] = {}
    topic_subtopics: dict[str, list[str]] = {}

    for topic in topics:
        detail = topic_details.get(topic)

        if detail is None:
            # Try a generic title match.
            detail = next(
                (
                    item
                    for title, item in topic_details.items()
                    if (
                        title.lower() == topic.lower()
                        or title.lower() in topic.lower()
                        or topic.lower() in title.lower()
                    )
                ),
                {},
            )

        topic_pages[topic] = set(
            detail.get("pages") or []
        )

        topic_subtopics[topic] = [
            _clean_heading(str(value))
            for value in (
                detail.get("subtopics") or []
            )
            if _clean_heading(str(value))
        ]

    # ------------------------------------------------------------
    # Topic terminology.
    # ------------------------------------------------------------
    topic_terms = {
        topic: _topic_terms(
            topic,
            intelligence.get("subtopics") or [],
        )
        for topic in topics
    }

    # Add topic-specific subtopics to the local terminology.
    for topic in topics:
        topic_terms[topic].extend(
            top_keywords(
                " ".join(
                    [
                        topic,
                        *topic_subtopics.get(
                            topic,
                            [],
                        ),
                    ]
                ),
                limit=16,
            )
        )
        topic_terms[topic] = list(
            dict.fromkeys(
                topic_terms[topic]
            )
        )

    # ------------------------------------------------------------
    # Determine which topics own each page.
    # ------------------------------------------------------------
    page_owners: dict[int, list[str]] = {}

    for topic in topics:
        for page in topic_pages.get(topic, set()):
            page_owners.setdefault(
                page,
                [],
            ).append(topic)

    # ------------------------------------------------------------
    # Assign every source block.
    # ------------------------------------------------------------
    topic_blocks: dict[
        str,
        list[tuple[int, dict[str, Any]]],
    ] = {
        topic: []
        for topic in topics
    }

    current_major: str | None = None

    for block_index, block in enumerate(blocks):
        page = int(
            block.get("page_number") or 1
        )
        heading = _clean_heading(
            block.get("heading") or ""
        )
        content = (
            block.get("text") or ""
        ).strip()

        if not content:
            continue

        # --------------------------------------------------------
        # 1. A heading that exactly matches a major topic starts a
        # new topic in the source flow.
        # --------------------------------------------------------
        direct_topic = next(
            (
                topic
                for topic in topics
                if _heading_matches_topic(
                    heading,
                    topic,
                )
            ),
            None,
        )

        if direct_topic:
            current_major = direct_topic

        # --------------------------------------------------------
        # 2. A structural child heading can also establish the
        # parent topic. Prefer the most specific matching parent.
        # --------------------------------------------------------
        if heading and not direct_topic:
            child_matches = []

            for topic in topics:
                candidates = [
                    *topic_subtopics.get(
                        topic,
                        [],
                    ),
                ]

                if any(
                    candidate
                    and _heading_matches_topic(
                        heading,
                        candidate,
                    )
                    for candidate in candidates
                ):
                    child_matches.append(topic)

            if len(child_matches) == 1:
                current_major = child_matches[0]

        # --------------------------------------------------------
        # 3. If the source heading is generic and no parent has been
        # established yet, use unique page ownership.
        # --------------------------------------------------------
        if current_major is None:
            owners = page_owners.get(
                page,
                [],
            )

            if len(owners) == 1:
                current_major = owners[0]

        # --------------------------------------------------------
        # 4. If the current topic is known, keep the block there.
        # This preserves the source's actual heading flow and is
        # stronger than keyword-only assignment.
        # --------------------------------------------------------
        if current_major is not None:
            topic_blocks[
                current_major
            ].append(
                (
                    block_index,
                    block,
                )
            )
            continue

        # --------------------------------------------------------
        # 5. Last-resort local keyword scoring.
        # --------------------------------------------------------
        scored: list[tuple[float, str]] = []

        for topic in topics:
            context = f"{heading} {content}"

            score = _block_score(
                topic,
                {
                    **block,
                    "text": context,
                },
                topic_terms.get(
                    topic,
                    [],
                ),
            )

            if page in topic_pages.get(
                topic,
                set(),
            ):
                score += 0.50

            scored.append(
                (
                    score,
                    topic,
                )
            )

        if scored:
            scored.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            best_score, best_topic = scored[0]

            if best_score >= 0.15:
                current_major = best_topic
                topic_blocks[
                    best_topic
                ].append(
                    (
                        block_index,
                        block,
                    )
                )

    # ------------------------------------------------------------
    # Build one section per major topic.
    # ------------------------------------------------------------
    sections: list[dict[str, Any]] = []

    for topic in topics:
        selected_pairs = topic_blocks.get(
            topic,
            [],
        )

        if not selected_pairs:
            continue

        selected_pairs.sort(
            key=lambda pair: pair[0]
        )

        selected = [
            block
            for _, block in selected_pairs
        ]

        text_parts: list[str] = []

        for block in selected:
            heading = _clean_heading(
                block.get("heading") or ""
            )
            content = (
                block.get("text") or ""
            ).strip()

            if not content:
                continue

            if heading:
                text_parts.append(
                    f"{heading}\n{content}"
                )
            else:
                text_parts.append(
                    content
                )

        source_text = "\n\n".join(
            text_parts
        ).strip()

        if not source_text:
            continue

        pages = sorted(
            set(
                int(block.get("page_number") or 1)
                for block in selected
            )
        )

        source_names = [
            block.get("source_filename")
            for block in selected
            if block.get("source_filename")
        ]

        section_source = (
            source_names[0]
            if source_names
            and len(set(source_names)) == 1
            else filename
        )

        related_topics = [
            item
            for item in (
                intelligence.get("subtopics") or []
            )
            if (
                keyword_overlap(
                    topic,
                    item,
                ) > 0
                or topic.lower() in item.lower()
                or item.lower() in topic.lower()
            )
        ][:8]

        sections.append(
            {
                "section_id": (
                    f"section-{len(sections) + 1}"
                ),
                "title": topic,
                "raw_text": source_text,
                "page_numbers": pages or [1],
                "source_filename": section_source,
                "concept_group": topic,
                "section_type": (
                    "workflow"
                    if topic in (
                        intelligence.get(
                            "workflow_sections"
                        ) or []
                    )
                    else "concept"
                ),
                "learning_objectives": [
                    (
                        f"Explain {topic} "
                        "clearly in exam language."
                    ),
                    (
                        f"Connect {topic} "
                        "with its related concepts, "
                        "examples and practical use."
                    ),
                ],
                "related_topics": related_topics,
                "concept_keywords": top_keywords(
                    f"{topic} {source_text}",
                    limit=12,
                ),
                "exam_priority_topics": [
                    item
                    for item in (
                        intelligence.get(
                            "exam_priority_topics"
                        ) or []
                    )
                    if (
                        keyword_overlap(
                            topic,
                            item,
                        ) > 0
                        or topic.lower() in item.lower()
                        or item.lower() in topic.lower()
                    )
                ][:10],
            }
        )

    # Never return a dangerously small/distorted structure.
    if len(sections) < 2:
        return _build_heading_sections(
            blocks,
            filename,
        )

    return sections



def build_semantic_sections(
    text: str,
    intelligence: dict[str, Any],
    filename: str,
) -> list[dict[str, Any]]:
    """
    Pass 2:
    Build coherent learning sections from the document-level
    intelligence map, with a safe heading-based fallback.
    """

    blocks = _collect_blocks(
        text
    )

    sections = create_learning_sections(
        blocks,
        intelligence,
        filename,
    )

    sections = merge_related_concepts(
        sections
    )

    return preserve_topic_flow(
        sections,
        intelligence,
    )
