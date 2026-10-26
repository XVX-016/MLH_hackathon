"""Low-level LLM client and hashing cache for videograph.

Uses Gemini API with:
1. Exact disk/memory caching based on SHA256 of prompt + model + config.
2. Structured JSON response enforcement.
3. Automatic single retry on JSON parse or Pydantic validation failure.
4. Strict API key retrieval from environment variables (GEMINI_API_KEY or GOOGLE_API_KEY).
"""

from __future__ import annotations
import os
import json
import hashlib
from typing import Type, TypeVar, Optional, Any
from pathlib import Path
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

CACHE_DIR = Path.home() / ".videograph_cache" / "llm"


def get_api_key() -> str:
    """Read API key from environment variables or .env file."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return key.strip() if key else ""



def compute_cache_key(prompt: str, model: str) -> str:
    """Generate SHA256 content hash for caching."""
    hasher = hashlib.sha256()
    hasher.update(model.encode("utf-8"))
    hasher.update(prompt.encode("utf-8"))
    return hasher.hexdigest()


def read_cache(cache_key: str) -> Optional[str]:
    """Retrieve cached response if present."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def write_cache(cache_key: str, content: str) -> None:
    """Persist raw LLM response text in content-addressed cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _extract_json_substring(text: str) -> str:
    """Extract substring enclosed between outer braces or markdown json fence."""
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[7:]
    elif stripped.startswith("```"):
        stripped = stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    stripped = stripped.strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def call_llm_raw(prompt: str, model: str = "gemini-2.5-flash") -> str:
    """Call Google GenAI SDK with environment key and content caching."""
    cache_key = compute_cache_key(prompt, model)
    cached = read_cache(cache_key)
    if cached:
        return cached

    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "Neither GEMINI_API_KEY nor GOOGLE_API_KEY is set in environment. "
            "Please set GEMINI_API_KEY before running LLM operations."
        )

    # Use google.genai Client
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        # Primary requested model is Gemma 4 / Gemini
        import time

        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            model,
        ]
        last_error = None

        for m in models_to_try:
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                    )
                    text = response.text or ""
                    if text:
                        write_cache(cache_key, text)
                        return text
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    # If model is experiencing temporary high demand, back off briefly
                    if "503" in err_str or "UNAVAILABLE" in err_str:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break

        raise RuntimeError(f"All LLM candidate models failed. Last error: {last_error}")

    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")



def call_llm_json(
    prompt: str,
    schema_cls: Type[T],
    model: str = "gemini-2.5-flash",
    max_retries: int = 1,
) -> T:
    """Execute LLM call and validate against Pydantic schema with one retry."""
    current_prompt = prompt
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        raw_text = call_llm_raw(current_prompt, model=model)
        json_str = _extract_json_substring(raw_text)

        try:
            parsed = json.loads(json_str)
            validated = schema_cls.model_validate(parsed)
            return validated
        except (json.JSONDecodeError, ValidationError) as err:
            last_error = err
            if attempt < max_retries:
                # One retry with correction instruction
                current_prompt = (
                    f"{prompt}\n\n"
                    f"CRITICAL ERROR in your previous response:\n{str(err)}\n\n"
                    f"Please output STRICTLY valid JSON complying with the requested schema. No conversational preamble."
                )

    raise ValueError(f"Failed to parse and validate LLM output after retry: {last_error}")
