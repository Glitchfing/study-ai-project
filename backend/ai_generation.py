from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from groq import Groq
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent

# Groq model currently available to this project
GROQ_MODEL = os.environ.get(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)

LLM_PRIMARY_PROVIDER = os.environ.get(
    "LLM_PRIMARY_PROVIDER",
    "groq",
).lower().strip()

DEFAULT_TEMPERATURE = float(
    os.environ.get("GROQ_TEMPERATURE", "0.25")
)

# Output caps are important for predictable latency and token usage.
DEFAULT_MAX_OUTPUT_TOKENS = int(
    os.environ.get("STUDYAI_MAX_OUTPUT_TOKENS", "6000")
)

_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}
_MAX_CACHE_ITEMS = int(
    os.environ.get("STUDYAI_LLM_CACHE_ITEMS", "128")
)

_CLIENT: Groq | None = None
_GEMINI_CLIENT: genai.Client | None = None



def _load_local_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


def has_llm_support() -> bool:
    """Return True when at least one supported LLM provider is configured."""
    return bool(
        os.environ.get("GROQ_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )


def _has_groq() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def _has_gemini() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _client() -> Groq:
    global _CLIENT

    if not _has_groq():
        raise RuntimeError("GROQ_API_KEY is not configured.")

    if _CLIENT is None:
        _CLIENT = Groq(
            api_key=os.environ.get("GROQ_API_KEY")
        )

    return _CLIENT




def _gemini_client() -> genai.Client:
    global _GEMINI_CLIENT

    if not _has_gemini():
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    if _GEMINI_CLIENT is None:
        _GEMINI_CLIENT = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY")
        )

    return _GEMINI_CLIENT


def _is_provider_error_recoverable(error: Exception) -> bool:
    """
    Decide whether it is reasonable to try the secondary provider.

    We use Gemini only as a controlled fallback. This prevents one
    provider's quota/rate-limit/outage from breaking note generation.
    """
    message = str(error).lower()

    markers = (
        "429",
        "rate limit",
        "rate_limit",
        "quota",
        "tokens per minute",
        "tokens per day",
        "tpm",
        "tpd",
        "resource exhausted",
        "temporarily unavailable",
        "service unavailable",
        "timeout",
        "timed out",
        "internal server error",
        "503",
        "502",
        "500",
    )

    return any(marker in message for marker in markers)


def _provider_order() -> list[str]:
    """Return primary provider followed by the other provider."""
    available = []

    if _has_groq():
        available.append("groq")

    if _has_gemini():
        available.append("gemini")

    if not available:
        return []

    if LLM_PRIMARY_PROVIDER in available:
        return [LLM_PRIMARY_PROVIDER] + [
            provider
            for provider in available
            if provider != LLM_PRIMARY_PROVIDER
        ]

    return available


def _cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _remember(key: str, value: dict[str, Any]) -> dict[str, Any]:
    _RESPONSE_CACHE[key] = value
    if len(_RESPONSE_CACHE) > _MAX_CACHE_ITEMS:
        _RESPONSE_CACHE.pop(next(iter(_RESPONSE_CACHE)))
    return value


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _generate_with_groq(
    prompt: str,
    *,
    temperature: float,
    max_output_tokens: int,
) -> str:
    response = _client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_output_tokens,
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("No response returned from Groq.")

    return content


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a generic JSON Schema into the subset accepted by Gemini.

    Gemini rejects both `additional_properties` and
    `additionalProperties` in response schemas, so both are removed
    recursively.
    """

    if not isinstance(schema, dict):
        return schema

    result: dict[str, Any] = {}

    for key, value in schema.items():

        # Unsupported JSON Schema metadata / object constraints in Gemini API.
        if key in {
            "additional_properties",
            "additionalProperties",
            "$schema",
            "$defs",
            "definitions",
            "default",
            "examples",
            "example",
            "deprecated",
            "readOnly",
            "writeOnly",
            "maxItems",
            "minItems",
            "maxLength",
            "minLength",
            "pattern",
        }:
            continue

        if key == "properties" and isinstance(value, dict):
            result["properties"] = {
                name: _gemini_schema(child)
                for name, child in value.items()
                if isinstance(child, dict)
            }

        elif key == "items" and isinstance(value, dict):
            result["items"] = _gemini_schema(value)

        elif isinstance(value, dict):
            result[key] = _gemini_schema(value)

        elif isinstance(value, list):
            result[key] = [
                _gemini_schema(item)
                if isinstance(item, dict)
                else item
                for item in value
            ]

        else:
            result[key] = value

    return result


def _generate_with_gemini(
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    *,
    temperature: float,
    max_output_tokens: int,
) -> str:
    """Generate structured JSON with Gemini using a compatible schema."""

    safe_schema = _gemini_schema(schema)

    prompt = (
        f"SYSTEM:\n{system_prompt}\n\n"
        f"USER:\n{user_prompt}\n\n"
        "Return ONLY the requested JSON object. "
        "Do not include markdown or explanatory text."
    )

    response = _gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=safe_schema,
        ),
    )

    if not response.text:
        raise ValueError("No response returned from Gemini.")

    return response.text


def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    *,
    images: list[dict[str, str]] | None = None,
    temperature: float | None = None,
    cache: bool = True,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """
    Generate structured JSON with a controlled Groq -> Gemini fallback.

    Provider policy:
      1. Use the configured primary provider (Groq by default).
      2. If it fails because of quota/rate-limit/service availability,
         try the other configured provider once.
      3. Never merge outputs from both providers. The first successful
         provider owns the final result for that request.
    """
    if not has_llm_support():
        raise RuntimeError(
            "No LLM provider is configured. Set GROQ_API_KEY and/or GEMINI_API_KEY."
        )

    # The current note-generation path is text-based. Keep the images
    # argument in the public API so callers remain compatible.
    if images:
        print(
            "[LLM PROVIDER] Image inputs were supplied; "
            "text fallback path will be used for this request."
        )

    temp = DEFAULT_TEMPERATURE if temperature is None else temperature
    output_limit = max(
        256,
        int(
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        ),
    )

    providers = _provider_order()
    if not providers:
        raise RuntimeError("No usable LLM provider is configured.")

    errors: list[str] = []

    for index, provider in enumerate(providers):

        cache_key = _cache_key(
            provider,
            GROQ_MODEL if provider == "groq" else GEMINI_MODEL,
            schema_name,
            schema,
            system_prompt,
            user_prompt,
            images or [],
        )

        if cache and cache_key in _RESPONSE_CACHE:
            return _RESPONSE_CACHE[cache_key]

        try:
            print(
                f"[LLM PROVIDER] {provider.upper()} "
                f"for {schema_name}"
            )

            if provider == "groq":
                prompt = (
                    f"SYSTEM:\n{system_prompt}\n\n"
                    f"USER:\n{user_prompt}\n\n"
                    "IMPORTANT:\n"
                    "Return ONLY valid JSON. Do not include markdown, comments, "
                    "or prose outside the JSON object.\n\n"
                    f"JSON Schema ({schema_name}):\n"
                    f"{json.dumps(schema, indent=2)}"
                )
                content = _generate_with_groq(
                    prompt,
                    temperature=temp,
                    max_output_tokens=output_limit,
                )
            else:
                content = _generate_with_gemini(
                    system_prompt,
                    user_prompt,
                    schema,
                    temperature=temp,
                    max_output_tokens=output_limit,
                )

            parsed = _extract_json(content)

            if not isinstance(parsed, dict):
                raise ValueError(
                    f"{provider} returned JSON, but it was not an object."
                )

            print(
                f"[LLM PROVIDER SUCCESS] {provider.upper()}"
            )

            return (
                _remember(cache_key, parsed)
                if cache
                else parsed
            )

        except Exception as exc:

            errors.append(
                f"{provider}: {type(exc).__name__}: {exc}"
            )

            # If another provider exists, only fall back for errors that
            # look like provider availability/quota problems.
            if index < len(providers) - 1:
                if _is_provider_error_recoverable(exc):
                    next_provider = providers[index + 1]
                    print(
                        f"[LLM FALLBACK] {provider.upper()} unavailable; "
                        f"switching to {next_provider.upper()}"
                    )
                    continue

            raise RuntimeError(
                "LLM generation failed.\n"
                + "\n".join(errors)
            ) from exc


async def async_generate_structured_json(
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    *,
    images: list[dict[str, str]] | None = None,
    temperature: float | None = None,
    cache: bool = True,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        generate_structured_json,
        system_prompt,
        user_prompt,
        schema_name,
        schema,
        images=images,
        temperature=temperature,
        cache=cache,
        max_output_tokens=max_output_tokens,
    )


def image_bytes_to_data_url(image_bytes: bytes, mime_type: str = "image/png") -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"