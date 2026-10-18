from __future__ import annotations

import hashlib
import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from ai_generation import generate_structured_json, has_llm_support
from note_store import get_note_record

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORE_PATH = DATA_DIR / "mind_maps.json"
_STORE_LOCK = threading.RLock()
MAX_NODES = 80
MAX_DEPTH = 6

MIND_MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "parent_id": {"type": ["string", "null"]},
                    "label": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "source_pages": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["id", "parent_id", "label", "type", "description", "key_points", "examples", "source_pages"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["source", "target", "label"],
            },
        },
    },
    "required": ["nodes", "edges"],
}


def _load_store() -> dict[str, Any]:
    with _STORE_LOCK:
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}


def _save_store(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STORE_PATH.with_suffix(".tmp")
    with _STORE_LOCK:
        temporary.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(STORE_PATH)


def _clean(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _source_material(note: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    package = note.get("package") or {}
    normalized = note.get("normalized") or {}
    normalized_note = normalized.get("note") or {}
    sections = package.get("sections") or normalized.get("sections") or normalized_note.get("sections") or []
    material_sections: list[dict[str, Any]] = []

    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        title = _clean(section.get("title") or section.get("heading") or section.get("topic") or f"Section {index + 1}", 140)
        text_parts = [
            section.get("content"),
            section.get("educational_explanation"),
            section.get("explanation"),
            section.get("notes", {}).get("cornell", {}).get("notes") if isinstance(section.get("notes"), dict) else None,
        ]
        text_parts.extend(section.get("key_points") or [])
        text_parts.extend(section.get("definitions") or [])
        text_parts.extend(section.get("important_notes") or [])
        text_parts.extend(section.get("examples") or [])
        body = "\n".join(_clean(part, 1600) for part in text_parts if part)
        pages = section.get("page_numbers") or section.get("source_pages") or []
        material_sections.append({
            "title": title,
            "text": body[:3600],
            "pages": [int(page) for page in pages if str(page).isdigit()][:20],
        })

    # Static notes and older records may only have format-specific content.
    if not material_sections:
        content = note.get("content") or {}
        for fmt in ("outline", "cornell", "sentence", "chart"):
            value = content.get(fmt)
            if isinstance(value, dict):
                if fmt == "outline":
                    for section in value.get("sections") or []:
                        title = _clean(section.get("heading") or "Topic", 140)
                        points = section.get("points") or []
                        material_sections.append({"title": title, "text": "\n".join(map(str, points))[:3000], "pages": []})
                elif fmt == "cornell":
                    text = "\n".join(str(value.get(key) or "") for key in ("notes", "summary", "cue"))
                    if text.strip():
                        material_sections.append({"title": _clean(value.get("title") or note.get("topic") or "Study notes"), "text": text[:6000], "pages": []})
            elif isinstance(value, str) and value.strip():
                material_sections.append({"title": _clean(note.get("topic") or note.get("title") or "Study notes"), "text": value[:6000], "pages": []})

    title = _clean(package.get("document_title") or normalized_note.get("title") or note.get("title") or note.get("topic") or "Study topic", 180)
    return title, material_sections[:120]


def _topic_sections(sections: list[dict[str, Any]], topic: str | None) -> list[dict[str, Any]]:
    if not topic:
        return sections
    query = topic.casefold().strip()
    exact = [section for section in sections if query in section["title"].casefold()]
    if exact:
        return exact
    words = {word for word in re.findall(r"[a-z0-9]+", query) if len(word) > 2}
    scored = []
    for section in sections:
        text = f'{section["title"]} {section["text"]}'.casefold()
        score = sum(1 for word in words if word in text)
        if score:
            scored.append((score, section))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [section for _, section in scored[:8]]


def _version(note: dict[str, Any], topic: str | None) -> str:
    source = note.get("package") or note.get("normalized") or note.get("content") or {}
    raw = json.dumps({"source": source, "topic": (topic or "").casefold()}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _safe_id(value: Any, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", _clean(value, 100)).strip("-").lower()
    return (slug or fallback)[:80]


def _fallback_map(root_label: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [{
        "id": "root",
        "parent_id": None,
        "label": root_label,
        "type": "topic",
        "description": "Main topic derived from the saved study material.",
        "key_points": [],
        "examples": [],
        "source_pages": sorted({p for section in sections for p in section["pages"]})[:20],
    }]
    seen: set[str] = set()
    for index, section in enumerate(sections):
        label = _clean(section["title"], 100)
        key = label.casefold()
        if not label or key in seen or len(nodes) >= MAX_NODES:
            continue
        seen.add(key)
        section_id = _safe_id(label, f"section-{index}")
        if any(node["id"] == section_id for node in nodes):
            section_id = f"{section_id}-{index}"
        sentences = [part.strip(" •-\t") for part in re.split(r"(?<=[.!?])\s+|\n+", section["text"]) if part.strip()]
        points = []
        for sentence in sentences:
            sentence = _clean(sentence, 180)
            if sentence and sentence.casefold() != label.casefold() and sentence not in points:
                points.append(sentence)
            if len(points) >= 3:
                break
        nodes.append({
            "id": section_id,
            "parent_id": "root",
            "label": label,
            "type": "concept",
            "description": _clean(section["text"], 320),
            "key_points": points,
            "examples": [],
            "source_pages": section["pages"],
        })
        # Extract a small set of meaningful sub-concepts from bullets/sentences.
        child_seen: set[str] = set()
        for child_index, sentence in enumerate(sentences[1:]):
            child_label = _clean(sentence, 65).rstrip(".:")
            child_key = child_label.casefold()
            if len(child_label) < 4 or child_key in child_seen or len(nodes) >= MAX_NODES:
                continue
            child_seen.add(child_key)
            child_id = _safe_id(f"{section_id}-{child_label}", f"{section_id}-child-{child_index}")
            if any(node["id"] == child_id for node in nodes):
                continue
            nodes.append({
                "id": child_id,
                "parent_id": section_id,
                "label": child_label,
                "type": "detail",
                "description": _clean(sentence, 300),
                "key_points": [],
                "examples": [],
                "source_pages": section["pages"],
            })
            if len(child_seen) >= 3:
                break
    edges = [{"source": node["parent_id"], "target": node["id"], "label": "includes"} for node in nodes if node["parent_id"]]
    return {"nodes": nodes, "edges": edges}


def _validate_map(payload: dict[str, Any], root_label: str) -> dict[str, Any]:
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges") or []
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("Mind map must contain nodes.")
    raw_nodes = raw_nodes[:MAX_NODES]
    nodes: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        node_id = _safe_id(raw.get("id"), f"node-{index}")
        if node_id in ids:
            raise ValueError("Mind map contains duplicate node IDs.")
        ids.add(node_id)
        pages = []
        for page in raw.get("source_pages") or []:
            try:
                number = int(page)
                if number > 0:
                    pages.append(number)
            except (TypeError, ValueError):
                continue
        nodes.append({
            "id": node_id,
            "parent_id": _safe_id(raw.get("parent_id"), "") if raw.get("parent_id") else None,
            "label": _clean(raw.get("label"), 120) or f"Concept {index + 1}",
            "type": _clean(raw.get("type"), 30) or "concept",
            "description": _clean(raw.get("description"), 600),
            "key_points": [_clean(value, 220) for value in (raw.get("key_points") or []) if _clean(value, 220)][:8],
            "examples": [_clean(value, 220) for value in (raw.get("examples") or []) if _clean(value, 220)][:6],
            "source_pages": sorted(set(pages))[:30],
        })
    if not nodes:
        raise ValueError("Mind map contains no valid nodes.")
    roots = [node for node in nodes if node["parent_id"] is None]
    if len(roots) != 1:
        raise ValueError("Mind map must have exactly one root node.")
    root = roots[0]
    root["label"] = root_label or root["label"]
    for node in nodes:
        if node["parent_id"] and node["parent_id"] not in ids:
            raise ValueError(f"Unknown parent node: {node['parent_id']}")
        if node["parent_id"] == node["id"]:
            raise ValueError("A node cannot be its own parent.")

    by_id = {node["id"]: node for node in nodes}
    depths: dict[str, int] = {}
    def depth(node_id: str, trail: set[str] | None = None) -> int:
        if node_id in depths:
            return depths[node_id]
        trail = set(trail or ())
        if node_id in trail:
            raise ValueError("Mind map hierarchy contains a cycle.")
        trail.add(node_id)
        parent = by_id[node_id]["parent_id"]
        result = 0 if parent is None else depth(parent, trail) + 1
        if result > MAX_DEPTH:
            raise ValueError("Mind map hierarchy is too deep.")
        depths[node_id] = result
        return result
    for node in nodes:
        depth(node["id"])

    edges = []
    edge_keys: set[tuple[str, str]] = set()
    for raw in raw_edges:
        if not isinstance(raw, dict):
            continue
        source, target = _safe_id(raw.get("source"), ""), _safe_id(raw.get("target"), "")
        if source not in ids or target not in ids or source == target or (source, target) in edge_keys:
            continue
        edge_keys.add((source, target))
        edges.append({"source": source, "target": target, "label": _clean(raw.get("label") or "related to", 60)})
        if len(edges) >= 240:
            break
    for node in nodes:
        parent = node["parent_id"]
        if parent and (parent, node["id"]) not in edge_keys:
            edges.append({"source": parent, "target": node["id"], "label": "includes"})
            edge_keys.add((parent, node["id"]))
    return {"nodes": nodes, "edges": edges}


def _generate(note: dict[str, Any], note_id: str, topic: str | None) -> dict[str, Any]:
    title, all_sections = _source_material(note)
    sections = _topic_sections(all_sections, topic)
    if not sections:
        raise ValueError("No saved study content is available for this note or topic.")
    root_label = _clean(topic or note.get("topic") or title, 180)
    source_text = "\n\n".join(
        f'SECTION: {section["title"]}\nPAGES: {section["pages"]}\n{section["text"]}'
        for section in sections
    )[:18000]
    generation_method = "deterministic"
    payload: dict[str, Any]
    if has_llm_support() and source_text.strip():
        try:
            result = generate_structured_json(
                "You create accurate study mind maps from source material. Use only facts supported by the source. Create one root node, major concept nodes and concise detail nodes. Keep the hierarchy coherent, include page references only when supplied, and add cross-links only for genuinely related concepts. Never invent source pages.",
                f"Create a mind map for the topic: {root_label}.\n\nSOURCE MATERIAL:\n{source_text}",
                "study_mind_map",
                MIND_MAP_SCHEMA,
                temperature=0.15,
                max_output_tokens=4200,
            )
            payload = result
            generation_method = "llm"
        except Exception:
            payload = _fallback_map(root_label, sections)
            generation_method = "deterministic_fallback"
    else:
        payload = _fallback_map(root_label, sections)
        generation_method = "deterministic_fallback"
    try:
        graph = _validate_map(payload, root_label)
    except (ValueError, TypeError, KeyError):
        graph = _validate_map(_fallback_map(root_label, sections), root_label)
        generation_method = "deterministic_fallback"
    version = _version(note, topic)
    result = {
        "note_id": note_id,
        "topic": root_label,
        "source_version": version,
        "generation_method": generation_method,
        "nodes": graph["nodes"],
        "edges": graph["edges"],
    }
    return result


def get_saved_mind_map(note_id: str, topic: str | None = None) -> dict[str, Any] | None:
    note = get_note_record(note_id)
    if not note:
        raise KeyError("Note not found.")
    version = _version(note, topic)
    key = f"{note_id}::{(topic or '').casefold().strip()}"
    store = _load_store()
    saved = store.get(key)
    if not isinstance(saved, dict) or saved.get("source_version") != version:
        return None
    return deepcopy(saved)


def generate_mind_map(note_id: str, topic: str | None = None, *, force: bool = False) -> dict[str, Any]:
    note = get_note_record(note_id)
    if not note:
        raise KeyError("Note not found.")
    key = f"{note_id}::{(topic or '').casefold().strip()}"
    if not force:
        saved = get_saved_mind_map(note_id, topic)
        if saved:
            return saved
    result = _generate(note, note_id, topic)
    store = _load_store()
    store[key] = result
    _save_store(store)
    return deepcopy(result)
