from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from activity import record_activity

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    history: Optional[list] = []


# Keyword → response map (replace with LLM call in production)
RESPONSES = {
    "tokenization": (
        "**Tokenization** is the process of splitting raw text into smaller units called *tokens*.\n\n"
        "**Types:**\n"
        "• **Word-level** — split on whitespace/punctuation (`nltk.word_tokenize`)\n"
        "• **Sub-word (BPE/WordPiece)** — handles OOV by splitting unknown words into known sub-units\n"
        "• **Character-level** — treats every character as a token\n\n"
        "Modern models (BERT, GPT) use sub-word tokenisation for the best vocabulary–coverage trade-off."
    ),
    "bert": (
        "**BERT** (Bidirectional Encoder Representations from Transformers) is a pre-trained language model by Google (2018).\n\n"
        "**Key ideas:**\n"
        "• Uses a **Transformer encoder** stack (no decoder)\n"
        "• Pre-trained on **Masked LM** (predict hidden tokens) + **Next Sentence Prediction**\n"
        "• Bidirectional — reads left AND right context simultaneously\n\n"
        "**Fine-tuning:** Add a task-specific head and train on labelled data. Achieves SOTA on many NLP benchmarks."
    ),
    "decision tree": (
        "A **Decision Tree** recursively partitions the feature space:\n\n"
        "1. At each node, select the feature + threshold that maximises **information gain** (or minimises Gini impurity)\n"
        "2. Split data; recurse on each child\n"
        "3. Stop at max depth, min samples, or pure leaves\n\n"
        "**Pros:** Interpretable, no feature scaling needed\n"
        "**Cons:** Prone to overfitting → use pruning or ensemble methods (Random Forest)"
    ),
    "neural network": (
        "**Neural Networks** are function approximators composed of layers of neurons:\n\n"
        "• **Forward pass** — input → hidden layers (activation fn) → output\n"
        "• **Loss** — measure prediction error (cross-entropy, MSE)\n"
        "• **Backpropagation** — compute gradients via chain rule\n"
        "• **Optimiser** — SGD / Adam update weights to minimise loss\n\n"
        "Modern tricks: BatchNorm, Dropout, Residual connections, Learning rate schedules."
    ),
    "weak areas": (
        "Based on your quiz performance, your **weak areas** are:\n\n"
        "1. **Decision Trees** (68%) — Review splitting criteria & overfitting\n"
        "2. **Neural Networks** (74%) — Revisit backpropagation & activations\n"
        "3. **Random Forests** (Not yet tested) — Upcoming topic\n\n"
        "I recommend checking the **Revision Planner** for a structured schedule! 📅"
    ),
    "summarize": (
        "Here's a summary of your uploaded notes:\n\n"
        "**NLP Core Concepts** — Tokenization, Transformers, BERT, NER ✓\n"
        "**ML Models** — Decision Trees, Random Forest (needs review)\n"
        "**Data Structures** — Linked Lists, BST (strong)\n\n"
        "You've covered **82%** of NLP topics. Focus energy on ML Models this week!"
    ),
    "quiz": (
        "Sure! Quick quiz time 🎯\n\n"
        "**Q: What does BERT stand for?**\n\n"
        "A) Bidirectional Encoder Representations from Transformers\n"
        "B) Binary Encoded Recurrent Transformer\n"
        "C) Basic Encoding and Retrieval Technique\n\n"
        "Reply with A, B, or C — or head to the **Practice Quiz** tab for a full session!"
    ),
}

DEFAULT_RESPONSE = (
    "That's a great question! Based on your study materials, I can help you with "
    "NLP concepts, ML algorithms, and Data Structures.\n\nFor example, try asking:\n\n"
    "• *\"Explain tokenization\"*\n"
    "• *\"What is a decision tree?\"*\n"
    "• *\"Summarize my notes\"*\n\n"
    "Or use the quick buttons above! 👆"
)


def match_response(message: str) -> str:
    lower = message.lower()
    for key, reply in RESPONSES.items():
        if key in lower:
            return reply
    return DEFAULT_RESPONSE


@router.post("")
def chat(req: ChatRequest):
    """Accept a user message and return an AI response."""
    response = match_response(req.message)
    record_activity(
        "chat_message",
        message=req.message,
        topic=next((key for key in RESPONSES if key in req.message.lower()), None),
    )
    return {
        "response": response,
        "model": "stub",  # swap "stub" → "claude-sonnet-4-20250514" when wiring real LLM
    }
