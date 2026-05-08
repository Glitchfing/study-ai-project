from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from note_generation import format_package_for_view
from note_normalizer import normalize_generated_notes

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
NOTES_DB_PATH = DATA_DIR / "generated_notes.json"

STATIC_NOTES: dict[str, dict[str, Any]] = {
    "nlp-derivatives": {
        "id": "nlp-derivatives",
        "title": "NLP Core Concepts",
        "topic": "NLP",
        "updated": "2 hours ago",
        "source": "static",
        "content": {
            "cornell": {
                "title": "NLP Core Concepts - Cornell Notes",
                "format": "cornell",
                "cue": [
                    "What is tokenization?",
                    "How does BERT handle context?",
                    "Difference between NER and POS tagging?",
                ],
                "notes": (
                    "Tokenization splits raw text into tokens (words/sub-words/chars).\n\n"
                    "BERT uses bidirectional transformer encoders with masked language modelling (MLM) "
                    "and next sentence prediction (NSP).\n\n"
                    "Named Entity Recognition (NER) identifies real-world entities; "
                    "POS tagging labels grammatical roles.\n\n"
                    "Word2Vec, GloVe produce static embeddings; BERT/GPT produce contextual embeddings."
                ),
                "summary": (
                    "NLP pipelines transform raw text -> tokens -> embeddings -> task-specific heads. "
                    "Transformer-based models dominate benchmarks via self-attention mechanisms."
                ),
            },
            "outline": {
                "title": "NLP Core Concepts - Outline",
                "format": "outline",
                "sections": [
                    {
                        "heading": "1. Tokenization",
                        "points": [
                            "Word-level vs sub-word (BPE, WordPiece) vs character-level",
                            "Handles OOV words via sub-word splitting",
                            "Libraries: HuggingFace Tokenizers, NLTK, SpaCy",
                        ],
                    },
                    {
                        "heading": "2. Embeddings",
                        "points": [
                            "Static: Word2Vec (skip-gram, CBOW), GloVe, FastText",
                            "Contextual: ELMo (BiLSTM), BERT (Transformer encoder), GPT (decoder)",
                            "Dimensionality: typically 128-1024 dims",
                        ],
                    },
                    {
                        "heading": "3. Key Architectures",
                        "points": [
                            "Transformer: self-attention + feed-forward, positional encoding",
                            "BERT: masked LM + NSP pre-training, fine-tune downstream",
                            "GPT family: autoregressive decoder, in-context learning",
                        ],
                    },
                    {
                        "heading": "4. Downstream Tasks",
                        "points": [
                            "NER, POS, Relation Extraction (token classification)",
                            "Sentiment, Classification (sequence classification)",
                            "QA, Summarisation, Translation (seq2seq)",
                        ],
                    },
                ],
            },
            "mindmap": {
                "title": "NLP Core Concepts - Mind Map",
                "format": "mindmap",
                "root": "NLP Core Concepts",
                "branches": [
                    {
                        "name": "Tokenization",
                        "sub_branches": [
                            {"name": "Word-level"},
                            {"name": "Sub-word"},
                            {"name": "Character-level"},
                        ],
                    },
                    {
                        "name": "Embeddings",
                        "sub_branches": [
                            {"name": "Static"},
                            {"name": "Contextual"},
                        ],
                    },
                ],
            },
            "chart": {
                "title": "NLP Core Concepts - Comparison Chart",
                "format": "chart",
                "columns": ["Model", "Type", "Context", "Year", "Key Feature"],
                "rows": [
                    ["Word2Vec", "Static", "None", "2013", "Efficient skip-gram"],
                    ["GloVe", "Static", "None", "2014", "Global co-occurrence"],
                    ["ELMo", "Contextual", "BiLSTM", "2018", "Character CNN + LSTM"],
                    ["BERT", "Contextual", "Bidirectional", "2018", "Masked LM + NSP"],
                    ["GPT-2", "Contextual", "Left-to-right", "2019", "Large-scale CLM"],
                    ["RoBERTa", "Contextual", "Bidirectional", "2019", "Dynamic masking"],
                ],
            },
            "sentence": (
                "NLP Core Concepts covers tokenization, embeddings, and transformer-based architectures, "
                "with emphasis on how modern language models process context and support downstream tasks."
            ),
        },
        "package": {
            "document_title": "NLP Core Concepts",
            "total_sections": 1,
            "sections": [],
            "notes": {},
            "diagrams": [],
            "questions": [],
            "global_summary": "NLP Core Concepts is a focused static study note.",
            "difficulty_level": "intermediate",
            "recommended_revision_strategy": "Review the note format and use it as an example structure.",
        },
    },
    "ml-models": {
        "id": "ml-models",
        "title": "ML Models Overview",
        "topic": "ML",
        "updated": "Yesterday",
        "source": "static",
        "content": {
            "cornell": {
                "title": "ML Models Overview - Cornell Notes",
                "format": "cornell",
                "cue": [
                    "Bias-variance tradeoff?",
                    "When to use Random Forest vs XGBoost?",
                    "What is regularisation?",
                ],
                "notes": (
                    "Decision Trees: recursive feature splits via Gini impurity / information gain. "
                    "Prone to overfitting -> prune or ensemble.\n\n"
                    "Random Forests: bagging + random feature subsets. Reduces variance. "
                    "Good default for tabular data.\n\n"
                    "Gradient Boosting (XGBoost, LightGBM): sequential trees, each corrects residuals. "
                    "Better accuracy, slower training.\n\n"
                    "SVMs: maximum-margin hyperplane, kernel trick for non-linearity."
                ),
                "summary": (
                    "Ensemble methods dominate tabular benchmarks. "
                    "Deep learning excels on unstructured data. "
                    "Always tune hyperparameters with cross-validation."
                ),
            },
            "outline": {
                "title": "ML Models Overview - Outline",
                "format": "outline",
                "sections": [
                    {
                        "heading": "1. Tree-based Models",
                        "points": [
                            "Decision Tree: Gini / entropy splits, depth pruning",
                            "Random Forest: bagging, OOB error estimate",
                            "Gradient Boosting: learning rate, n_estimators, max_depth",
                        ],
                    },
                    {
                        "heading": "2. Support Vector Machines",
                        "points": [
                            "Hard-margin vs soft-margin (C parameter)",
                            "Kernels: linear, RBF, polynomial",
                            "Effective in high-dimensional spaces",
                        ],
                    },
                    {
                        "heading": "3. Neural Networks",
                        "points": [
                            "Backpropagation via chain rule",
                            "Activation functions: ReLU, sigmoid, tanh, GELU",
                            "Regularisation: dropout, weight decay, batch norm",
                        ],
                    },
                ],
            },
            "mindmap": {
                "title": "ML Models Overview - Mind Map",
                "format": "mindmap",
                "root": "ML Models Overview",
                "branches": [
                    {
                        "name": "Tree-based Models",
                        "sub_branches": [{"name": "Decision Tree"}, {"name": "Random Forest"}, {"name": "Boosting"}],
                    }
                ],
            },
            "chart": {
                "title": "ML Models - Comparison Chart",
                "format": "chart",
                "columns": ["Model", "Type", "Speed", "Interpretability", "Best For"],
                "rows": [
                    ["Decision Tree", "Tree", "Fast", "High", "Explainable baselines"],
                    ["Random Forest", "Ensemble", "Medium", "Medium", "General tabular"],
                    ["XGBoost", "Boosting", "Medium", "Low", "Competitions / kaggle"],
                    ["SVM", "Margin", "Slow", "Low", "Small high-dim datasets"],
                    ["Neural Network", "DL", "Slow", "None", "Unstructured data"],
                ],
            },
            "sentence": (
                "ML Models Overview compares tree-based methods, SVMs, and neural networks, "
                "highlighting trade-offs in accuracy, interpretability, and compute cost."
            ),
        },
        "package": {
            "document_title": "ML Models Overview",
            "total_sections": 1,
            "sections": [],
            "notes": {},
            "diagrams": [],
            "questions": [],
            "global_summary": "ML Models Overview is a focused static study note.",
            "difficulty_level": "intermediate",
            "recommended_revision_strategy": "Review the note format and use it as an example structure.",
        },
    },
}

GENERATED_NOTES: dict[str, dict[str, Any]] = {}


def _load_generated_notes() -> dict[str, dict[str, Any]]:
    if not NOTES_DB_PATH.exists():
        return {}
    try:
        data = json.loads(NOTES_DB_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_generated_notes() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DB_PATH.write_text(json.dumps(GENERATED_NOTES, indent=2), encoding="utf-8")


def _normalize_record(note_id: str, record: dict[str, Any]) -> dict[str, Any]:
    normalized_note = (record.get("normalized") or {}).get("note") or {}
    return {
        "id": note_id,
        "title": record["title"],
        "topic": record["topic"],
        "updated": record["updated"],
        "source": record.get("source", "generated"),
        "total_sections": normalized_note.get("total_sections"),
        "estimated_read_time": normalized_note.get("estimated_read_time"),
        "progress": normalized_note.get("progress", 0),
        "is_favorite": normalized_note.get("is_favorite", False),
        "last_opened": normalized_note.get("last_opened"),
    }


def register_generated_note(package: dict[str, Any], topic: str | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    topic_label = (topic or "UPLOAD").upper()
    normalized = normalize_generated_notes(package, topic_label)
    note_id = normalized["note"]["id"]
    GENERATED_NOTES[note_id] = {
        "id": note_id,
        "title": package["document_title"],
        "topic": topic_label,
        "updated": now,
        "source": "generated",
        "package": package,
        "normalized": normalized,
    }
    _save_generated_notes()
    return note_id


def list_notes() -> list[dict[str, Any]]:
    items = [
        _normalize_record(note_id, record)
        for note_id, record in STATIC_NOTES.items()
    ]
    items.extend(
        _normalize_record(note_id, record)
        for note_id, record in GENERATED_NOTES.items()
    )
    return items


def get_note_record(note_id: str) -> dict[str, Any] | None:
    if note_id in GENERATED_NOTES:
        return GENERATED_NOTES[note_id]
    return STATIC_NOTES.get(note_id)


def get_note_content(note_id: str, note_format: str) -> dict[str, Any]:
    record = get_note_record(note_id)
    if not record:
        return {}
    if record.get("source") == "generated":
        return format_package_for_view(record["package"], note_format)
    return deepcopy(record["content"].get(note_format) or record["content"].get("cornell") or {})


def get_normalized_note(note_id: str) -> dict[str, Any]:
    record = get_note_record(note_id)
    if not record:
        return {}
    return deepcopy(record.get("normalized") or {})


GENERATED_NOTES.update(_load_generated_notes())
