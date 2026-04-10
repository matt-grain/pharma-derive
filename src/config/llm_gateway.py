"""LLM gateway — single entry point for PydanticAI model creation.

All LLM construction goes through here. Agents never instantiate models directly.
"""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.config.settings import get_settings

_cached_model: OpenAIChatModel | None = None
_cached_key: str | None = None


def create_llm(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAIChatModel:
    """Create or return cached PydanticAI LLM model pointing to the AgentLens proxy."""
    global _cached_model, _cached_key
    settings = get_settings()
    resolved_url = base_url or settings.llm_base_url
    resolved_key = api_key or settings.llm_api_key
    resolved_model = model_name or settings.llm_model

    cache_key = f"{resolved_url}:{resolved_key}:{resolved_model}"
    if _cached_model is not None and _cached_key == cache_key:
        return _cached_model

    provider = OpenAIProvider(base_url=resolved_url, api_key=resolved_key)
    _cached_model = OpenAIChatModel(resolved_model, provider=provider)
    _cached_key = cache_key
    return _cached_model


def reset_llm_cache() -> None:
    """Reset the cached LLM model. Used in tests to ensure fresh state."""
    global _cached_model, _cached_key
    _cached_model = None
    _cached_key = None
