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
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Return (fragment_id, rationale).

        `context` may carry runtime hints (sim_time, here_uid, visible_agents,
        visible_items, last_activity, weekday) so the LLM can reason about the
        current situation in addition to persona+memory.
        """
        ...

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]: ...

    async def generate_dialog(
        self,
        speaker: dict[str, Any],
        listener: dict[str, Any],
        speaker_memories: list[str],
        situation: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate one short two-line dialog.

        Returns dict: {speaker_line, listener_line, topic, tone}.
        """
        ...

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        """Produce an omniscient-narrator paragraph for a finished sim day.

        Returns {zh, en, degraded}.
        """
        ...


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
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("MockLLMAdapter.choose_fragment: empty candidates")
        favs = set(persona.get("preferences", {}).get("favorite_tags", []) or [])
        visible = set((context or {}).get("visible_agents", []) or [])

        def score(c: dict[str, Any]) -> int:
            s = len(favs & set(c.get("tags", []) or []))
            # if someone is around and the fragment is "social", give a small bump
            if visible and "social" in (c.get("tags", []) or []):
                s += 1
            return s

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

    async def generate_dialog(
        self,
        speaker: dict[str, Any],
        listener: dict[str, Any],
        speaker_memories: list[str],
        situation: dict[str, Any],
    ) -> dict[str, Any]:
        sname = speaker.get("name") or speaker.get("id") or "对方"
        lname = listener.get("name") or listener.get("id") or "TA"
        return {
            "speaker_line": f"{lname}你好，最近怎么样？",
            "listener_line": f"还行，{sname}你呢？",
            "speaker_line_en": f"Hi {lname}, how have you been?",
            "listener_line_en": f"Doing OK, you {sname}?",
            "topic": "寒暄",
            "topic_en": "greetings",
            "tone": "friendly",
        }

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        head = bullets[:3] if bullets else ["（无事可记）"]
        zh = f"{day} 这一天，校园里共发生约 {stats.get('n_behaviors', 0)} 次行为、{stats.get('n_dialogs', 0)} 段对话。"
        en = f"On {day}, the campus saw roughly {stats.get('n_behaviors', 0)} actions and {stats.get('n_dialogs', 0)} conversations."
        if head:
            zh += " 例如：" + "；".join(h[:60] for h in head)
            en += " e.g. " + "; ".join(h[:60] for h in head)
        return {"zh": zh, "en": en, "degraded": True}


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
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("choose_fragment: empty candidates")
        prompt = self._render(
            "choose_fragment.j2",
            gap_minutes=gap_minutes,
            persona=persona,
            memories=memories,
            candidates=candidates,
            context=context or {},
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

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = (
            "You are the omniscient narrator of a campus simulation. Given a day's worth of "
            "raw event bullets, write ONE vivid paragraph in Chinese and ONE in English describing "
            "what happened that day on campus — pace, tensions, relationships, small details. "
            "Stay grounded in the bullets; don't invent named characters not present.\n\n"
            f"DAY: {day}\nSTATS: {stats}\nEVENTS (chronological):\n"
            + "\n".join(f"- {b}" for b in bullets)
            + "\n\nReturn STRICTLY this JSON: {\"zh\": \"<≤200汉字>\", \"en\": \"<≤180 words>\"}."
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"narrate_day: expected object, got {type(data).__name__}")
        return {
            "zh": str(data.get("zh", "")).strip(),
            "en": str(data.get("en", "")).strip(),
            "degraded": False,
        }

    async def generate_dialog(
        self,
        speaker: dict[str, Any],
        listener: dict[str, Any],
        speaker_memories: list[str],
        situation: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = self._render(
            "generate_dialog.j2",
            speaker=speaker,
            listener=listener,
            speaker_memories=speaker_memories,
            sim_time=situation.get("sim_time", "?"),
            weekday=situation.get("weekday", "?"),
            here_uid=situation.get("here_uid", "?"),
            here_name=situation.get("here_name", "?"),
            current_activity=situation.get("current_activity", "?"),
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"generate_dialog: expected object, got {type(data).__name__}")
        # Defensive defaults so callers can rely on the keys existing.
        return {
            "speaker_line": str(data.get("speaker_line", "")).strip() or "（无内容）",
            "listener_line": str(data.get("listener_line", "")).strip() or "（无回应）",
            "topic": str(data.get("topic", "")).strip() or "杂谈",
            "tone": str(data.get("tone", "neutral")).strip() or "neutral",
        }


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
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        async def _primary() -> tuple[str, str]:
            return await self.primary.choose_fragment(
                gap_minutes, persona, memories, candidates, context=context,
            )

        async def _fallback() -> tuple[str, str]:
            return await self.fallback.choose_fragment(
                gap_minutes, persona, memories, candidates, context=context,
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

    async def generate_dialog(
        self,
        speaker: dict[str, Any],
        listener: dict[str, Any],
        speaker_memories: list[str],
        situation: dict[str, Any],
    ) -> dict[str, Any]:
        async def _primary() -> dict[str, Any]:
            return await self.primary.generate_dialog(
                speaker, listener, speaker_memories, situation,
            )

        async def _fallback() -> dict[str, Any]:
            return await self.fallback.generate_dialog(
                speaker, listener, speaker_memories, situation,
            )

        result, degraded = await safe_call(_primary, _fallback)
        self._record("generate_dialog", degraded)
        return result

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        async def _primary() -> dict[str, Any]:
            return await self.primary.narrate_day(day, bullets, stats)

        async def _fallback() -> dict[str, Any]:
            return await self.fallback.narrate_day(day, bullets, stats)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("narrate_day", degraded)
        # propagate degraded flag into the payload too
        if isinstance(result, dict):
            result = {**result, "degraded": bool(result.get("degraded") or degraded)}
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
