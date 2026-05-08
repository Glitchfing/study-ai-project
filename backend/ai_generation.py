from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from groq import Groq

BASE_DIR = Path(__file__).resolve().parent


def _load_local_env() -> None:
    env_path = BASE_DIR / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'")
        )


_load_local_env()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

GROQ_MODEL = os.environ.get(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)


def has_llm_support() -> bool:
    return bool(GROQ_API_KEY)


client = Groq(api_key=GROQ_API_KEY)


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    *,
    images: list[dict[str, str]] | None = None,
) -> dict[str, Any]:

    prompt = f"""
SYSTEM:
{system_prompt}

USER:
{user_prompt}

IMPORTANT:
Return ONLY valid JSON.

JSON Schema:
{json.dumps(schema, indent=2)}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
    )

    text = response.choices[0].message.content

    if not text:
        raise ValueError("No response returned from Groq.")

    # Remove markdown JSON blocks if model adds them
    text = text.strip()

    if text.startswith("```json"):
        text = text.removeprefix("```json").removesuffix("```").strip()

    elif text.startswith("```"):
        text = text.removeprefix("```").removesuffix("```").strip()

    return json.loads(text)


def image_bytes_to_data_url(
    image_bytes: bytes,
    mime_type: str = "image/png"
) -> str:

    encoded = base64.b64encode(image_bytes).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"