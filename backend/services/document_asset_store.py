from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ASSETS_FILE = DATA_DIR / "document_assets.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ASSETS_FILE.exists():
        with open(ASSETS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load_all_assets() -> dict[str, Any]:
    _ensure_data_dir()
    try:
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[DOCUMENT ASSETS] Error reading {ASSETS_FILE}: {exc}")
        return {}


def _save_all_assets(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    try:
        with open(ASSETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[DOCUMENT ASSETS] Error writing {ASSETS_FILE}: {exc}")


def register_document_assets(
    document_id: str,
    filename: str,
    diagrams: list[dict[str, Any]] | None = None,
    page_count: int | None = None,
    size_kb: float | None = None,
) -> dict[str, Any]:
    """
    Persist document metadata and diagrams for future targeted retrieval.
    """
    if not document_id:
        return {}

    assets = _load_all_assets()
    entry = {
        "document_id": document_id,
        "filename": filename,
        "diagrams": diagrams or [],
        "page_count": page_count,
        "size_kb": size_kb,
    }
    assets[document_id] = entry
    _save_all_assets(assets)
    return entry


def get_document_assets(document_id: str) -> dict[str, Any] | None:
    """
    Retrieve stored document assets by document_id.
    """
    if not document_id:
        return None
    assets = _load_all_assets()
    return assets.get(document_id)


def get_document_diagrams(
    document_id: str,
    pages: list[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Get diagrams associated with a document_id, optionally filtered by page numbers.
    """
    doc = get_document_assets(document_id)
    if not doc:
        return []

    diagrams = doc.get("diagrams", [])
    if not pages:
        return diagrams

    page_set = set(pages)
    return [
        d for d in diagrams
        if d.get("page_number") in page_set or not d.get("page_number")
    ]


def list_all_document_assets() -> list[dict[str, Any]]:
    """
    Return a list of all indexed documents with asset summaries.
    """
    assets = _load_all_assets()
    return [
        {
            "document_id": doc_id,
            "filename": info.get("filename", "Untitled Document"),
            "diagram_count": len(info.get("diagrams", [])),
            "page_count": info.get("page_count"),
            "size_kb": info.get("size_kb"),
        }
        for doc_id, info in assets.items()
    ]
