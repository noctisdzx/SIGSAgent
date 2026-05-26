"""HTTP client for any OpenAI-compatible Chat Completions endpoint.

Hot-swappable: works with OpenAI, DeepSeek, Qwen-OpenAI-compatible, vLLM,
Ollama (`/v1/chat/completions`), etc., by just changing `LLM_BASE_URL`
and `LLM_API_KEY`.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.settings import get_settings


class OpenAICompatibleClient:
    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.llm_base_url.rstrip("/")
        self.api_key = s.llm_api_key
        self.model = s.llm_model
        self.timeout = s.llm_timeout

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        response_format: dict | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            body["response_format"] = response_format
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
