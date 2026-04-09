"""LLM gateway — single entry point for PydanticAI model creation.

All LLM construction goes through here. Agents never instantiate models directly.
"""

from __future__ import annotations

import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

_DEFAULT_BASE_URL = "http://localhost:8650/v1"
_DEFAULT_API_KEY = "not-needed-for-mailbox"
_DEFAULT_MODEL = "cdde-agent"


def create_llm(
    model_name: str = _DEFAULT_MODEL,
    base_url: str = _DEFAULT_BASE_URL,
    api_key: str = _DEFAULT_API_KEY,
) -> OpenAIChatModel:
    """Create a PydanticAI LLM model pointing to the AgentLens proxy.

    Environment variables override the defaults:
    - LLM_BASE_URL: proxy base URL
    - LLM_API_KEY: API key (not required for mailbox mode)
    - LLM_MODEL: model name registered in AgentLens
    """
    resolved_url = os.environ.get("LLM_BASE_URL", base_url)
    resolved_key = os.environ.get("LLM_API_KEY", api_key)
    resolved_model = os.environ.get("LLM_MODEL", model_name)

    provider = OpenAIProvider(base_url=resolved_url, api_key=resolved_key)
    return OpenAIChatModel(resolved_model, provider=provider)
