"""Atomic JSON persistence for recommendation lifecycle records.

The current application stores local learner data in JSON files. This store
follows that convention and keeps a bounded history. Multi-worker production
deployments should move these operations to a transactional database.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from learner_model import build_concept_mastery, build_topic_mastery
from quiz_attempt_store import list_quiz_attempts
from recommendation_service import build_recommendations
try:
    from recommendation_config import MAX_RECOMMENDATION_CANDIDATES
except ImportError:
    MAX_RECOMMENDATION_CANDIDATES = 100

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RECOMMENDATIONS_PATH = DATA_DIR / "recommendations.json"
MAX_HISTORY = 500
ACTIVE_STATUSES = {"pending", "in_progress"}
VALID_STATUSES = {"pending", "in_progress", "completed", "dismissed", "reevaluated"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> list[dict[str, Any]]:
    try:
        raw = json.loads(RECOMMENDATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict) and item.get("id")]


def _write(rows: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = RECOMMENDATIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows[-MAX_HISTORY:], ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(RECOMMENDATIONS_PATH)


def _signature(item: dict[str, Any]) -> str:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    payload = {
        "id": item.get("id"),
        "attempts": evidence.get("attempt_count", item.get("attempts")),
        "questions": evidence.get("question_count", item.get("question_count")),
        "mastery": evidence.get("mastery_pct", item.get("mastery_pct")),
        "trend": evidence.get("trend", item.get("trend")),
        "last_reviewed_at": evidence.get("last_reviewed_at"),
        "incorrect_count": evidence.get("incorrect_count"),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def upsert_recommendations(recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Upsert current candidates while preserving status until evidence changes."""
    saved = _read()
    by_id = {str(item["id"]): item for item in saved}
    now = _now()
    current_ids: set[str] = set()
    for candidate in recommendations:
        if not isinstance(candidate, dict) or not candidate.get("id"):
            continue
        rec_id = str(candidate["id"])
        current_ids.add(rec_id)
        prior = by_id.get(rec_id)
        row = dict(candidate)
        signature = _signature(row)
        if prior:
            old_signature = prior.get("evidence_signature") or _signature(prior)
            materially_changed = signature != old_signature
            row["created_at"] = prior.get("created_at") or row.get("created_at") or now
            row["updated_at"] = now
            previous_status = prior.get("status", "pending")
            # A recommendation that previously fell outside the ranked window
            # should become active again when it re-enters the candidate set.
            row["status"] = (
                "pending"
                if previous_status == "reevaluated"
                or (materially_changed and previous_status in {"completed", "dismissed"})
                else previous_status
            )
            row["status_history"] = list(prior.get("status_history") or [])
            if materially_changed and prior.get("status") in {"completed", "dismissed"}:
                row["status_history"].append({
                    "status": prior.get("status"), "at": prior.get("updated_at") or prior.get("created_at"),
                    "note": "Reopened because new learner evidence changed this recommendation."
                })
        else:
            row["created_at"] = row.get("created_at") or now
            row["updated_at"] = now
            row["status"] = "pending"
            row["status_history"] = []
        row["evidence_signature"] = signature
        by_id[rec_id] = row

    # Recommendations which fell out of the current ranked candidate set are
    # retained for history but no longer shown as active dashboard actions.
    for rec_id, prior in by_id.items():
        if rec_id not in current_ids and prior.get("status", "pending") in ACTIVE_STATUSES:
            prior["status"] = "reevaluated"
            prior["updated_at"] = now
            history = list(prior.get("status_history") or [])
            history.append({"status": "reevaluated", "at": now, "note": "No longer in the current top-ranked set."})
            prior["status_history"] = history
    _write(list(by_id.values()))
    return [by_id[str(item["id"])] for item in recommendations if item.get("id") and str(item["id"]) in by_id]


def list_recommendations(*, include_history: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    rows = _read()
    if not include_history:
        rows = [row for row in rows if row.get("status", "pending") in ACTIVE_STATUSES]
    return list(reversed(rows[-max(0, limit):]))


def get_recommendation(recommendation_id: str) -> dict[str, Any] | None:
    return next((row for row in _read() if str(row.get("id")) == recommendation_id), None)


def update_recommendation_status(recommendation_id: str, status: str) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported recommendation status: {status}")
    rows = _read()
    found = None
    now = _now()
    for row in rows:
        if str(row.get("id")) != recommendation_id:
            continue
        previous = row.get("status", "pending")
        if previous != status:
            history = list(row.get("status_history") or [])
            history.append({"status": status, "at": now, "previous_status": previous})
            row["status_history"] = history
            row["status"] = status
            row["updated_at"] = now
        found = row
        break
    if found:
        _write(rows)
    return found


def _load_pending_revision_tasks() -> list[dict[str, Any]]:
    """Load real saved planner tasks; never manufacture tasks from UI templates."""
    path = DATA_DIR / "revision_tasks.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [
        dict(task) for task in loaded
        if isinstance(task, dict)
        and task.get("id") is not None
        and not task.get("done")
        and task.get("status") not in {"completed", "cancelled", "skipped"}
    ]


def refresh_recommendations(
    *,
    attempts: list[dict[str, Any]] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Recompute ranked recommendations from persisted attempts and planner tasks."""
    current_attempts = attempts if attempts is not None else list_quiz_attempts(limit=1000)
    topics = build_topic_mastery(current_attempts)
    concepts = build_concept_mastery(current_attempts)
    try:
        from note_store import list_notes
        saved_notes = [note for note in list_notes() if isinstance(note, dict) and note.get("id") and note.get("source") == "generated"]
    except Exception:
        saved_notes = []

    def normalize_topic(value: Any) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    for topic_name, stats in topics.items():
        if stats.get("note_id"):
            continue
        match = next((note for note in saved_notes if normalize_topic(note.get("topic")) == normalize_topic(topic_name) or normalize_topic(note.get("title")) == normalize_topic(topic_name)), None)
        if match:
            stats["note_id"] = match.get("id")
            stats["note_title"] = match.get("title") or match.get("topic")

    candidates = build_recommendations(
        topics,
        concept_mastery=concepts,
        revision_tasks=_load_pending_revision_tasks(),
        note_topics=saved_notes,
        limit=max(MAX_RECOMMENDATION_CANDIDATES, limit * 10, limit),
    )
    persisted = upsert_recommendations(candidates)
    active = [item for item in persisted if item.get("status", "pending") in ACTIVE_STATUSES]
    return active[:limit]



def record_recommendation_outcome(recommendation_id: str, attempt: dict[str, Any]) -> dict[str, Any] | None:
    """Persist the linked quiz outcome without claiming the recommendation caused it."""
    rows = _read()
    target = next((row for row in rows if str(row.get("id")) == recommendation_id), None)
    if target is None or not isinstance(attempt, dict):
        return None

    concept = _normalize_label(target.get("concept"))
    topic = _normalize_label(target.get("topic"))
    responses = [
        item for item in (attempt.get("responses") or [])
        if isinstance(item, dict) and isinstance(item.get("is_correct"), bool)
    ]
    matched = []
    for response in responses:
        response_concept = _normalize_label(
            response.get("concept_id") or response.get("concept") or response.get("concept_tag")
        )
        response_topic = _normalize_label(response.get("topic") or response.get("section_title"))
        if concept and response_concept == concept:
            matched.append(response)
        elif not concept and topic and response_topic == topic:
            matched.append(response)

    if matched:
        correct_count = sum(1 for row in matched if row.get("is_correct") is True)
        response_count = len(matched)
        post_accuracy = correct_count / response_count
        outcome_scope = "concept" if concept else "topic"
    else:
        response_count = len(responses)
        post_accuracy = (
            max(0.0, min(100.0, float(attempt.get("score") or 0))) / 100.0
            if attempt.get("score") is not None else None
        )
        outcome_scope = "overall_quiz_only"

    evidence = target.get("evidence") if isinstance(target.get("evidence"), dict) else {}
    baseline = evidence.get("mastery_pct", target.get("mastery_pct"))
    baseline_pct = float(baseline) if isinstance(baseline, (int, float)) else None
    outcome = {
        "attempt_id": attempt.get("id"),
        "recorded_at": _now(),
        "scope": outcome_scope,
        "matched_response_count": response_count if matched else 0,
        "post_accuracy_pct": round(post_accuracy * 100, 1) if post_accuracy is not None else None,
        "baseline_mastery_pct": round(baseline_pct, 1) if baseline_pct is not None else None,
        "observed_change_percentage_points": (
            round(post_accuracy * 100 - baseline_pct, 1)
            if post_accuracy is not None and baseline_pct is not None and matched
            else None
        ),
        "interpretation": (
            "Observed follow-up performance; this comparison does not establish causation."
            if matched else
            "Quiz saved, but no response matched the recommended concept/topic, so targeted improvement is unknown."
        ),
    }
    history = list(target.get("outcomes") or [])
    history.append(outcome)
    target["outcomes"] = history[-50:]
    previous = target.get("status", "pending")
    target["status"] = "completed"
    target["updated_at"] = outcome["recorded_at"]
    status_history = list(target.get("status_history") or [])
    status_history.append({
        "status": "completed",
        "at": outcome["recorded_at"],
        "previous_status": previous,
        "note": "Linked quiz attempt submitted.",
    })
    target["status_history"] = status_history
    target["last_outcome"] = outcome
    _write(rows)
    return outcome


def _normalize_label(value: Any) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
