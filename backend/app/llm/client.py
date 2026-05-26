"""HTTP client for any OpenAI-compatible Chat Completions endpoint.

Hot-swappable: works with OpenAI, DeepSeek, Qwen-OpenAI-compatible, vLLM,
Ollama (`/v1/chat/completions`), etc., by just changing `LLM_BASE_URL`
and `LLM_API_KEY`.

Defaults are tuned for DeepSeek (`deepseek-chat`):
- Narrative completions use `temperature=0.6` (the module default).
- JSON-shaped completions should use `temperature=0.2` and pass
  `response_format={"type": "json_object"}` — DeepSeek honors the
  OpenAI structured-output flag.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.settings import get_settings


# Sane defaults — callers may override per call.
DEFAULT_NARRATIVE_TEMPERATURE = 0.6
DEFAULT_JSON_TEMPERATURE = 0.2


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
        temperature: float | None = None,
        response_format: dict | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """Call `/chat/completions`.

        - `json_mode=True` is shorthand for `response_format={"type": "json_object"}`
          and lowers the default temperature to `DEFAULT_JSON_TEMPERATURE` if the
          caller didn't pass an explicit value.
        - When neither `json_mode` nor `response_format` is set and `temperature`
          is None, falls back to `DEFAULT_NARRATIVE_TEMPERATURE`.
        """
        if json_mode and response_format is None:
            response_format = {"type": "json_object"}

        if temperature is None:
            temperature = (
                DEFAULT_JSON_TEMPERATURE if response_format is not None
                else DEFAULT_NARRATIVE_TEMPERATURE
            )

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

    @staticmethod
    def extract_text(payload: dict[str, Any]) -> str:
        """Extract the first message's content from a chat-completions payload."""
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover
            raise ValueError(f"Unexpected chat completion payload shape: {payload!r}") from exc
