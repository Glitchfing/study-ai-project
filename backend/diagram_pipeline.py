from __future__ import annotations

from pathlib import Path
from uuid import uuid4

try:
    import fitz

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DIAGRAM_DIR = STATIC_DIR / "diagrams"
DIAGRAM_KEYWORDS = ("diagram", "architecture", "flow", "model", "lifecycle", "layer", "pipeline")


def _nearby_text(page, image_rect) -> str:
    blocks = page.get_text("blocks")
    candidates = []
    for block in blocks:
        x0, y0, x1, y1, text, *_ = block
        text_value = (text or "").strip()
        if not text_value:
            continue
        vertical_gap = min(abs(y1 - image_rect.y0), abs(y0 - image_rect.y1))
        intersects_horizontally = not (x1 < image_rect.x0 or x0 > image_rect.x1)
        if vertical_gap <= 120 or intersects_horizontally:
            candidates.append((vertical_gap, text_value))
    candidates.sort(key=lambda item: item[0])
    return " ".join(text for _, text in candidates[:3]).strip()


def _looks_like_diagram(width: float, height: float, nearby_text: str) -> bool:
    area = width * height
    keyword_match = any(keyword in nearby_text.lower() for keyword in DIAGRAM_KEYWORDS)
    return keyword_match or area >= 30000


def _diagram_caption(page_number: int, nearby_text: str) -> str:
    if nearby_text:
        compact = " ".join(nearby_text.split())
        return compact[:140]
    return f"Diagram extracted from page {page_number}"


def extract_diagrams_from_pdf(file_bytes: bytes, note_id: str) -> list[dict]:
    if not HAS_PYMUPDF:
        return []

    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    diagrams = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    for page_index in range(len(doc)):
        page = doc[page_index]
        for image_index, image in enumerate(page.get_images(full=True)):
            xref = image[0]
            rects = page.get_image_rects(xref)
            rect = rects[0] if rects else fitz.Rect(0, 0, 0, 0)
            nearby_text = _nearby_text(page, rect) if rects else ""
            if not _looks_like_diagram(rect.width, rect.height, nearby_text):
                continue

            extracted = doc.extract_image(xref)
            image_bytes = extracted.get("image")
            ext = extracted.get("ext", "png")
            if not image_bytes:
                continue

            filename = f"{note_id}_p{page_index + 1}_{image_index + 1}_{uuid4().hex}.{ext}"
            file_path = DIAGRAM_DIR / filename
            file_path.write_bytes(image_bytes)

            diagrams.append(
                {
                    "id": uuid4().hex,
                    "type": "image",
                    "content": "",
                    "image_path": str(file_path.relative_to(BASE_DIR)).replace("\\", "/"),
                    "image_url": f"/static/diagrams/{filename}",
                    "page_number": page_index + 1,
                    "caption": _diagram_caption(page_index + 1, nearby_text),
                    "context_text": nearby_text,
                    "ocr_text": nearby_text,
                    "diagram_type": "document_diagram",
                    "mermaid_code": "",
                    "explanation": "",
                }
            )

    doc.close()
    return diagrams


def _section_match_score(section: dict, diagram: dict) -> int:
    score = 0
    section_pages = set(section.get("page_numbers") or [])
    if diagram.get("page_number") in section_pages:
        score += 5

    caption = f"{diagram.get('caption', '')} {diagram.get('context_text', '')}".lower()
    for topic in section.get("topics", []):
        if str(topic).lower() in caption:
            score += 3
    title = str(section.get("title", "")).lower()
    if title and title in caption:
        score += 4
    return score


def _default_mermaid(section_title: str, caption: str) -> str:
    return "\n".join(
        [
            "flowchart TD",
            f"  A[{section_title}] --> B[{caption}]",
            "  B --> C[Structure or flow]",
            "  C --> D[Exam explanation]",
        ]
    )


def attach_diagrams_to_sections(package: dict, diagrams: list[dict]) -> dict:
    sections = package.get("sections") or []
    if not diagrams:
        package["diagrams"] = []
        return package
    if not sections:
        package["diagrams"] = diagrams
        return package

    for diagram in diagrams:
        best_section = max(sections, key=lambda section: _section_match_score(section, diagram))
        best_section.setdefault("diagrams", []).append(diagram)
        diagram["section_id"] = best_section.get("section_id")
        if not diagram.get("explanation"):
            diagram["explanation"] = (
                f"This diagram belongs with {best_section.get('title', 'the current section')}. "
                "Use it to explain the structure, flow, or relationship shown in the uploaded material."
            )
        if not diagram.get("mermaid_code"):
            diagram["mermaid_code"] = _default_mermaid(best_section.get("title", "Section"), diagram.get("caption", "Diagram"))

    package["sections"] = sections
    package["diagrams"] = diagrams
    return package
