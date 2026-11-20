"""Encapsulate Gemini requests and validate generated content."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from config import GEMINI_API_KEY

DEFAULT_FLASHCARD_COUNT = 5
MAX_FLASHCARD_COUNT = 30


@lru_cache(maxsize=1)
def _client() -> Any:
    """Create and cache the Gemini client on first use.

    Returns:
        An initialized Gemini client.

    Raises:
        RuntimeError: If ``GEMINI_API_KEY`` is not configured.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    from google import genai

    return genai.Client(api_key=GEMINI_API_KEY)


def _flashcard_count(content: str, requested_count: int | None) -> int:
    """Resolve a bounded number of flashcards for generated content.

    Args:
        content: Source text used to estimate coverage needs.
        requested_count: User-supplied number, if any.

    Returns:
        A count between one and ``MAX_FLASHCARD_COUNT``.
    """
    if requested_count is not None:
        return max(1, min(MAX_FLASHCARD_COUNT, requested_count))
    prompt = (
        "Choose how many flashcards are needed to cover this content. "
        f"Return only an integer from 1 to {MAX_FLASHCARD_COUNT}.\n\n{content}"
    )
    response = _client().models.generate_content(model="gemini-2.0-flash", contents=prompt)
    try:
        return max(1, min(MAX_FLASHCARD_COUNT, int(response.text.strip())))
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_FLASHCARD_COUNT


def generate_flashcards(content: str, requested_count: int | None = None) -> list[dict[str, str]]:
    """Generate and validate flashcards from source text.

    Args:
        content: Source text to study.
        requested_count: Optional desired card count.

    Returns:
        Valid question and answer records.

    Raises:
        ValueError: If the model response does not contain valid flashcards.
    """
    count = _flashcard_count(content, requested_count)
    prompt = (
        f"Generate {count} high-quality flashcards from the content below. "
        "Return only a JSON array of objects with question and answer fields.\n\n"
        f"Content:\n{content}"
    )
    response = _client().models.generate_content(model="gemini-2.0-flash", contents=prompt)
    text = (response.text or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("The model response did not contain a JSON array.")
    cards = json.loads(text[start : end + 1])
    if not isinstance(cards, list):
        raise ValueError("The model response must be a JSON array.")
    valid_cards = [
        {"question": item["question"].strip(), "answer": item["answer"].strip()}
        for item in cards
        if isinstance(item, dict)
        and isinstance(item.get("question"), str)
        and isinstance(item.get("answer"), str)
        and item["question"].strip()
        and item["answer"].strip()
    ]
    if not valid_cards:
        raise ValueError("The model response did not contain valid flashcards.")
    return valid_cards


def generate_study_guide(content: str) -> str:
    """Generate a structured study guide from source text.

    Args:
        content: Source text to transform into a study guide.

    Returns:
        Generated study guide text.
    """
    prompt = (
        "Create a clear, comprehensive study guide from the source. Organize it "
        "with an overview, sections, key terms, examples, and a summary. Preserve "
        "important information and do not add unsupported facts.\n\n"
        f"Source:\n{content}"
    )
    response = _client().models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return (response.text or "").strip()
