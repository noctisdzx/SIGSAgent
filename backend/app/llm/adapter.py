"""Abstract LLM interface used by memory / decision modules,
plus concrete adapters:

- `MockLLMAdapter`: deterministic, no-network, the ultimate fallback.
- `DeepSeekAdapter`: real DeepSeek (OpenAI-compatible) client driven by
  Jinja2 prompts in `app/llm/prompts/`.
- `SafeLLMAdapter`: wraps a primary + fallback. Each method runs primary
  with `with_fallback`; on failure swaps in the fallback's result and
  exposes `last_degraded` so callers can tag artifacts. Existing call
  sites that still do their own `try/except` keep working too.
- `build_llm_adapter()`: factory used by `app.main` /
  `app.sim.loop` — returns a Mock adapter when the API key is empty,
  else a `SafeLLMAdapter(DeepSeekAdapter(), MockLLMAdapter())`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.settings import get_settings

from .client import (
    DEFAULT_JSON_TEMPERATURE,
    DEFAULT_NARRATIVE_TEMPERATURE,
    OpenAICompatibleClient,
)
from .retry import safe_call


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class LLMAdapter(Protocol):
    async def summarize_memories(self, texts: list[str]) -> str: ...

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Return (fragment_id, rationale)."""
        ...

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Mock fallback
# ---------------------------------------------------------------------------
class MockLLMAdapter:
    """No-network deterministic fallback.

    Outputs are stable for given inputs so unit tests can pin them.
    """

    async def summarize_memories(self, texts: list[str]) -> str:
        if not texts:
            return "(empty)"
        return "summary: " + " | ".join(t[:60] for t in texts)

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("MockLLMAdapter.choose_fragment: empty candidates")
        favs = set(persona.get("preferences", {}).get("favorite_tags", []) or [])

        def score(c: dict[str, Any]) -> int:
            return len(favs & set(c.get("tags", []) or []))

        best = max(candidates, key=score)
        return best["id"], "mock: best tag-overlap with persona"

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]:
        return [
            {"subject": agent_id, "predicate": "did", "object": ev[:30]}
            for ev in events
        ]


# ---------------------------------------------------------------------------
# DeepSeek (OpenAI-compatible) adapter
# ---------------------------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _build_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
        keep_trailing_newline=True,
    )


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE | re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    """DeepSeek occasionally wraps JSON in ```json fences even when asked
    not to; strip them defensively before json.loads."""
    return _FENCE_RE.sub("", text).strip()


def _parse_json_object(text: str) -> Any:
    """Parse text that should contain a single JSON object. Raises ValueError."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Try to salvage: find the first { ... } / [ ... ] block.
        start = min(
            (cleaned.find(c) for c in "{[" if cleaned.find(c) != -1),
            default=-1,
        )
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if 0 <= start < end:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM did not return valid JSON: {text!r}") from exc


class DeepSeekAdapter:
    """OpenAI-compatible chat adapter pointed at DeepSeek by default.

    All 3 methods speak the same protocol; raise on bad output so the
    `with_fallback` wrapper can cleanly degrade to `MockLLMAdapter`.
    """

    def __init__(
        self,
        client: OpenAICompatibleClient | None = None,
        env: Environment | None = None,
    ) -> None:
        self.client = client or OpenAICompatibleClient()
        self.env = env or _build_jinja_env()

    # ----- helpers -----

    def _render(self, template_name: str, **ctx: Any) -> str:
        return self.env.get_template(template_name).render(**ctx)

    async def _chat_text(
        self,
        prompt: str,
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if temperature is None:
            temperature = (
                DEFAULT_JSON_TEMPERATURE if json_mode else DEFAULT_NARRATIVE_TEMPERATURE
            )
        payload = await self.client.chat(
            messages=messages,
            temperature=temperature,
            json_mode=json_mode,
        )
        return self.client.extract_text(payload)

    # ----- protocol -----

    async def summarize_memories(self, texts: list[str]) -> str:
        prompt = self._render("compress_stm.j2", lines=texts)
        out = await self._chat_text(prompt, json_mode=False)
        out = _strip_code_fences(out)
        if not out:
            raise ValueError("DeepSeek returned empty summary")
        # First non-empty line; the prompt asks for one sentence.
        for line in out.splitlines():
            line = line.strip().strip('"').strip("'")
            if line:
                return line
        return out

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("choose_fragment: empty candidates")
        prompt = self._render(
            "choose_fragment.j2",
            gap_minutes=gap_minutes,
            persona=persona,
            memories=memories,
            candidates=candidates,
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"choose_fragment: expected object, got {type(data).__name__}")
        fid = data.get("id")
        rationale = str(data.get("rationale", "")).strip() or "(no rationale)"
        valid_ids = {c["id"] for c in candidates}
        if fid not in valid_ids:
            raise ValueError(
                f"choose_fragment: returned id {fid!r} not in candidates {sorted(valid_ids)}"
            )
        return fid, rationale

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]:
        if not events:
            return []
        prompt = self._render("extract_triplets.j2", agent_id=agent_id, events=events)
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        # We accept either {"triplets": [...]} (preferred) or a bare list.
        if isinstance(data, dict) and "triplets" in data:
            items = data["triplets"]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError(f"extract_triplets: unexpected JSON shape: {data!r}")

        if not isinstance(items, list):
            raise ValueError("extract_triplets: triplets is not a list")

        cleaned: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            subj = raw.get("subject")
            pred = raw.get("predicate")
            obj = raw.get("object")
            if not (isinstance(subj, str) and isinstance(pred, str) and isinstance(obj, str)):
                continue
            cleaned.append(
                {
                    "subject": subj,
                    "predicate": pred,
                    "object": obj,
                    "location_uid": raw.get("location_uid"),
                    "tone": raw.get("tone"),
                }
            )
        if not cleaned:
            raise ValueError("extract_triplets: no valid triplet in response")
        return cleaned


# ---------------------------------------------------------------------------
# SafeLLMAdapter — primary + fallback, exposes `last_degraded`
# ---------------------------------------------------------------------------
class SafeLLMAdapter:
    """Wraps a primary adapter with a fallback adapter.

    For each protocol method:
        result, degraded = safe_call(primary.method, fallback.method)
    The `degraded` flag is exposed via `self.last_degraded` and via
    `self.last_degraded_by_method` for fine-grained inspection.

    Existing call sites in the codebase still do their own try/except
    around `LLMAdapter` calls — both styles coexist.
    """

    def __init__(self, primary: LLMAdapter, fallback: LLMAdapter) -> None:
        self.primary = primary
        self.fallback = fallback
        self.last_degraded: bool = False
        self.last_degraded_by_method: dict[str, bool] = {}

    def _record(self, method: str, degraded: bool) -> None:
        self.last_degraded = degraded
        self.last_degraded_by_method[method] = degraded

    async def summarize_memories(self, texts: list[str]) -> str:
        async def _primary() -> str:
            return await self.primary.summarize_memories(texts)

        async def _fallback() -> str:
            return await self.fallback.summarize_memories(texts)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("summarize_memories", degraded)
        return result

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        async def _primary() -> tuple[str, str]:
            return await self.primary.choose_fragment(
                gap_minutes, persona, memories, candidates
            )

        async def _fallback() -> tuple[str, str]:
            return await self.fallback.choose_fragment(
                gap_minutes, persona, memories, candidates
            )

        result, degraded = await safe_call(_primary, _fallback)
        self._record("choose_fragment", degraded)
        return result

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]:
        async def _primary() -> list[dict[str, Any]]:
            return await self.primary.extract_triplets(agent_id, events)

        async def _fallback() -> list[dict[str, Any]]:
            return await self.fallback.extract_triplets(agent_id, events)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("extract_triplets", degraded)
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_PLACEHOLDER_KEYS = {"", "sk-...", "your-api-key", "changeme", "placeholder"}
_PLACEHOLDER_PREFIXES = ("sk-xxx",)  # common "fill-me-in" placeholder shape


def _looks_like_placeholder_key(key: str) -> bool:
    if not key:
        return True
    norm = key.strip().lower()
    if norm in {k.lower() for k in _PLACEHOLDER_KEYS}:
        return True
    return any(norm.startswith(p) for p in _PLACEHOLDER_PREFIXES)


def build_llm_adapter() -> LLMAdapter:
    """Return the best available `LLMAdapter`.

    - If `LLM_API_KEY` is empty/placeholder → pure `MockLLMAdapter`.
    - Else → `SafeLLMAdapter(DeepSeekAdapter(), MockLLMAdapter())` so any
      DeepSeek hiccup falls back transparently to the mock.
    """
    s = get_settings()
    if _looks_like_placeholder_key(s.llm_api_key):
        return MockLLMAdapter()
    return SafeLLMAdapter(primary=DeepSeekAdapter(), fallback=MockLLMAdapter())
