"""LLM client, abstract adapter, mock fallback, and retry helpers."""

from .adapter import (
    DeepSeekAdapter,
    LLMAdapter,
    MockLLMAdapter,
    SafeLLMAdapter,
    build_llm_adapter,
    build_narrate_day_messages,
    parse_narrate_day_response,
)
from .client import OpenAICompatibleClient
from .retry import safe_call, with_fallback

__all__ = [
    "LLMAdapter",
    "MockLLMAdapter",
    "DeepSeekAdapter",
    "SafeLLMAdapter",
    "build_llm_adapter",
    "build_narrate_day_messages",
    "parse_narrate_day_response",
    "OpenAICompatibleClient",
    "with_fallback",
    "safe_call",
]
