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

    async def choose_insert_event(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Return (event_id, rationale). Mirrors `choose_fragment` but the
        candidates carry a natural-language `description`, `tags`,
        `duration_minutes` and a `from`→`to` trip.
        """
        ...

    async def describe_insert_event(self, event: dict[str, Any]) -> dict[str, str]:
        """Author a bilingual one-line description for a raw insert event.

        Returns {"description_zh": ..., "description_en": ...}.
        """
        ...

    async def describe_activity(
        self,
        persona: dict[str, Any],
        activity: str,
        situation: dict[str, Any],
    ) -> dict[str, str]:
        """Rephrase a raw schedule/fragment label into a short, in-character,
        scene-aware sentence for THIS npc (so the UI shows a personalised
        description rather than the generic fragment label).

        `situation` carries sim_time, weekday, here_uid, here_name.
        Returns {"description_zh": ..., "description_en": ...}.
        """
        ...

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]: ...

    async def choose_dialog_target(
        self,
        speaker: dict[str, Any],
        candidates: list[dict[str, Any]],
        situation: dict[str, Any],
    ) -> tuple[str | None, str]:
        """Pick WHO (if anyone) the speaker talks to this moment.

        `candidates` are co-located agents, each with `id`, `name`,
        `archetype` and `minutes_since_last_talk` (None = never). Returns
        `(target_id, rationale)`; `target_id` may be None to stay silent.
        """
        ...

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

    async def generate_mutter(
        self,
        speaker: dict[str, Any],
        situation: dict[str, Any],
        memories: list[str],
    ) -> dict[str, Any]:
        """Generate one short line of inner monologue (the dialog channel's
        `Mutter` state) for when the speaker has no one to talk to.

        `situation` carries sim_time, weekday, here_uid, here_name,
        current_activity and body_action. Returns dict:
        {line, line_en, mood}.
        """
        ...

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        """Produce a literary recap for a finished sim day.

        Returns a dict with at least::

            {
              "zh": "<one-paragraph synopsis>",
              "en": "<one-paragraph synopsis>",
              "degraded": bool,
            }

        Rich adapters additionally return::

            {
              "title_zh", "title_en",
              "protagonist": {"name", "name_en", "why_zh", "why_en"},
              "supporting": [{"name", "name_en", "role_zh", "role_en"}, ...],
              "story_zh", "story_en",          # multi-paragraph short story
              "tomorrow_zh", "tomorrow_en",    # predictions for next day
            }
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

    async def choose_insert_event(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("MockLLMAdapter.choose_insert_event: empty candidates")
        favs = set(persona.get("preferences", {}).get("favorite_tags", []) or [])
        visible = set((context or {}).get("visible_agents", []) or [])

        def score(c: dict[str, Any]) -> int:
            s = len(favs & set(c.get("tags", []) or []))
            if visible and "social" in (c.get("tags", []) or []):
                s += 1
            return s

        best = max(candidates, key=score)
        return best["id"], "mock: best tag-overlap with persona"

    async def describe_insert_event(self, event: dict[str, Any]) -> dict[str, str]:
        start = event.get("start_name", "?")
        end = event.get("end_name", "?")
        return {
            "description_zh": f"从{start}前往{end}，忙里偷闲走一趟。",
            "description_en": f"A quick trip from {start} to {end} during free time.",
        }

    async def describe_activity(
        self,
        persona: dict[str, Any],
        activity: str,
        situation: dict[str, Any],
    ) -> dict[str, str]:
        name = persona.get("name") or persona.get("id") or "TA"
        here = situation.get("here_name") or situation.get("here_uid") or "此处"
        act = (activity or "休息").strip()
        return {
            "description_zh": f"{name}正在{here}{act}。",
            "description_en": f"{name} is busy with {act} at {here}.",
        }

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]:
        return [
            {"subject": agent_id, "predicate": "did", "object": ev[:30]}
            for ev in events
        ]

    async def choose_dialog_target(
        self,
        speaker: dict[str, Any],
        candidates: list[dict[str, Any]],
        situation: dict[str, Any],
    ) -> tuple[str | None, str]:
        if not candidates:
            return None, "mock: no candidates"
        # Prefer someone we've never spoken to; otherwise the least-recently
        # talked-to. If everyone was engaged very recently, stay silent so the
        # same pair doesn't loop every tick.
        def recency(c: dict[str, Any]) -> float:
            m = c.get("minutes_since_last_talk")
            return float("inf") if m is None else float(m)
        best = max(candidates, key=recency)
        m = best.get("minutes_since_last_talk")
        if m is not None and m < 30:
            return None, "mock: everyone spoken to recently — stay silent"
        return best["id"], "mock: least-recently-talked partner"

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

    async def generate_mutter(
        self,
        speaker: dict[str, Any],
        situation: dict[str, Any],
        memories: list[str],
    ) -> dict[str, Any]:
        activity = situation.get("current_activity") or "发呆"
        return {
            "line": f"该专心{activity}了……",
            "line_en": f"Better focus on {activity} now...",
            "mood": "neutral",
        }

    async def narrate_day(
        self,
        day: str,
        bullets: list[str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        head = bullets[:3] if bullets else ["（无事可记）"]
        zh_synopsis = (
            f"{day} 这一天，校园里共发生约 {stats.get('n_behaviors', 0)} 次行为、"
            f"{stats.get('n_dialogs', 0)} 段对话。"
        )
        en_synopsis = (
            f"On {day}, the campus saw roughly {stats.get('n_behaviors', 0)} actions "
            f"and {stats.get('n_dialogs', 0)} conversations."
        )
        if head:
            zh_synopsis += " 例如：" + "；".join(h[:60] for h in head)
            en_synopsis += " e.g. " + "; ".join(h[:60] for h in head)

        actor_stats = stats.get("activity_top") or []
        protagonist_name = ""
        protagonist_name_en = ""
        if actor_stats:
            top = actor_stats[0]
            protagonist_name = str(top.get("name") or top.get("id") or "")
            protagonist_name_en = str(top.get("name_en") or protagonist_name)

        supporting: list[dict[str, str]] = []
        for a in actor_stats[1:4]:
            supporting.append({
                "name": str(a.get("name") or a.get("id") or ""),
                "name_en": str(a.get("name_en") or a.get("name") or a.get("id") or ""),
                "role_zh": "活跃的同伴",
                "role_en": "active companion",
            })

        story_zh = (
            f"清晨，校园在 {protagonist_name or '人群'} 的脚步声里醒来。\n\n"
            f"{zh_synopsis}\n\n"
            "（LLM 降级中：本段为占位短篇。）"
        )
        story_en = (
            f"Dawn broke over the campus with {protagonist_name_en or 'the crowd'} on the move.\n\n"
            f"{en_synopsis}\n\n"
            "(LLM degraded: placeholder story.)"
        )
        tomorrow_zh = "明日预测暂不可用（LLM 降级中）。"
        tomorrow_en = "Tomorrow predictions unavailable (LLM degraded)."

        return {
            "title_zh": f"{day} · 校园速写",
            "title_en": f"{day} · A Campus Sketch",
            "protagonist": {
                "name": protagonist_name,
                "name_en": protagonist_name_en,
                "why_zh": "今日活动最多的 NPC。",
                "why_en": "Most active NPC of the day.",
            },
            "supporting": supporting,
            "story_zh": story_zh,
            "story_en": story_en,
            "tomorrow_zh": tomorrow_zh,
            "tomorrow_en": tomorrow_en,
            "zh": zh_synopsis,
            "en": en_synopsis,
            "degraded": True,
        }


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


# ---------------------------------------------------------------------------
# Shared literary-prompt builder for narrate_day
# ---------------------------------------------------------------------------
# Why a shared builder:
#   Both `DeepSeekAdapter.narrate_day` here AND the inline adapter in
#   `app.main._make_llm_adapter` need to send the SAME high-quality prompt;
#   otherwise edits drift apart silently (we hit that exact bug — main.py's
#   `_Adapter` was shadowing this module's narrate_day).
#
# Craft choices baked into the prompt (drawn from working LLM creative-writing
# playbooks):
#   - Expert persona ("literary fiction novelist + showrunner") to filter
#     training-data style.
#   - Chain-of-thought scaffold: model first fills a private "beats" plan that
#     is NEVER rendered to the user, then writes the story informed by it.
#   - Show-don't-tell + Four-Modality (visual / auditory / kinesthetic /
#     meaning) hard rules.
#   - Three-act structure baked into the story brief.
#   - Hard length floors enforced both in words AND with an anti-laziness
#     clause ("any value shorter than the floor is INVALID, regenerate").
# ---------------------------------------------------------------------------
NARRATE_DAY_SYSTEM = (
    "You are an experienced literary-fiction novelist and showrunner. You write "
    "vivid, character-driven short stories with psychological depth, atmospheric "
    "immersion and thematic resonance. You are also bilingual and write equally "
    "well in 现代汉语 and contemporary literary English.\n\n"
    "CRAFT RULES (non-negotiable):\n"
    "  1. SHOW, don't tell. Embed emotion through specific body language, "
    "     gesture, dialogue, and sensory detail — never bare statements like "
    "     '他很紧张' or 'She felt sad'.\n"
    "  2. FOUR-MODALITY pass per scene: weave in (a) visual specifics — light, "
    "     objects, gestures, (b) auditory — voices, ambient sound, silence, "
    "     (c) kinesthetic — temperature, fatigue, taste, posture, "
    "     (d) meaning — the small internal recognition that shifts the beat.\n"
    "  3. THIRD-PERSON OMNISCIENT but warm and intimate; restrained, no purple "
    "     prose. Vary sentence length for pacing — short for tension, longer "
    "     for introspection.\n"
    "  4. ANCHOR every beat in the raw event log: do NOT invent named characters; "
    "     use Chinese names verbatim in BOTH languages (do not romanise).\n"
    "  5. THREE-ACT structure for the story: setup → escalation → reveal/turn. "
    "     The supporting cast each gets a clear function (catalyst, foil, "
    "     mentor, confidant, comic relief).\n"
    "  6. ANTI-LAZINESS: if you find yourself shortening the story to dodge the "
    "     length floor, STOP and expand with another sensory scene. Outputs "
    "     under the floor are INVALID and you must regenerate before returning.\n"
    "  7. NEVER mention 'simulation', 'NPC', 'agent', 'JSON', 'prompt', or any "
    "     tooling vocabulary inside the prose.\n"
)


def _build_narrate_day_user_prompt(
    day: str,
    bullets: list[str],
    stats: dict[str, Any],
) -> str:
    """Build the user message for narrate_day, with the strict output contract."""
    actor_stats = stats.get("activity_top") or []
    actor_hint_lines = [
        f"  - {a.get('name', '?')} (id={a.get('id', '?')}): "
        f"{a.get('n_behaviors', 0)} actions, {a.get('n_dialogs', 0)} dialogs"
        for a in actor_stats[:12]
    ]
    actor_hint = "\n".join(actor_hint_lines) or "  (no actor stats)"
    clean_stats = {k: v for k, v in stats.items() if k != "activity_top"}

    return (
        f"DAY: {day}\n"
        f"STATS: {clean_stats}\n"
        f"TOP ACTORS (sorted by activity — choose protagonist & cast from here):\n"
        f"{actor_hint}\n\n"
        "EVENTS (chronological, capped):\n"
        + "\n".join(f"- {b}" for b in bullets)
        + "\n\n"
        "TASK: Turn this day into a literary short story (a self-contained "
        "chapter), in both Chinese and English. Use the CRAFT RULES from the "
        "system message.\n\n"
        "OUTPUT — return ONE JSON object, no preamble, no code fences. "
        "ALL keys are REQUIRED and must satisfy the length floors:\n\n"
        "{\n"
        "  \"beats\": [\n"
        "    \"<≤30字 私有大纲: 第1幕 setup>\",\n"
        "    \"<≤30字 第2幕 escalation>\",\n"
        "    \"<≤30字 第3幕 reveal/turn>\"\n"
        "  ],   // chain-of-thought scaffold — keep terse, used to plan the story\n"
        "  \"title_zh\": \"<10–20 字 文学感章节标题>\",\n"
        "  \"title_en\": \"<8–14 word literary chapter title>\",\n"
        "  \"protagonist\": {\n"
        "    \"name\": \"<中文名 from TOP ACTORS>\",\n"
        "    \"name_en\": \"<English name or same 中文名>\",\n"
        "    \"why_zh\": \"<≤40字 为什么 Ta 是今日主角>\",\n"
        "    \"why_en\": \"<≤30 words why they anchor today>\"\n"
        "  },\n"
        "  \"supporting\": [   // 2–4 配角，每人一个清晰戏剧功能\n"
        "    {\"name\": \"<中文名>\", \"name_en\": \"<英文或中文名>\",\n"
        "     \"role_zh\": \"<≤20字 在剧情里的功能>\",\n"
        "     \"role_en\": \"<≤15 words story function>\"}\n"
        "  ],\n"
        "  \"story_zh\": \"<HARD FLOOR ≥ 500 汉字, 4–6 段, 用 \\n\\n 分段。\n"
        "                    全知温暖旁白，现在时态，文学化但克制。\n"
        "                    至少包含 3 处感官细节(视/听/触/嗅味)和 1 处对白。\n"
        "                    严格遵守 SHOW-DON'T-TELL 与四感官规则。>\",\n"
        "  \"story_en\": \"<HARD FLOOR ≥ 350 English words, 4–6 paragraphs, "
        "separated by \\n\\n. Past tense, warm omniscient. At least 3 sensory "
        "details and 1 line of dialog. Same SHOW-DON'T-TELL rules.>\",\n"
        "  \"tomorrow_zh\": \"<2–4 条明日预测，每条独立成行 (用 \\n 分隔)。\n"
        "                       基于今日未解的张力、日程、关系做出具体但不绝对的预测。>\",\n"
        "  \"tomorrow_en\": \"<2–4 tomorrow predictions, one per line, \\n separated.\n"
        "                       Specific but not certain — teasers, not certainties.>\"\n"
        "}\n\n"
        "VALIDATION: count characters/words of story_zh and story_en yourself "
        "before returning. If story_zh < 500 汉字 OR story_en < 350 words, "
        "REGENERATE with more vivid scenes before responding. No exceptions."
    )


def build_narrate_day_messages(
    day: str,
    bullets: list[str],
    stats: dict[str, Any],
) -> list[dict[str, str]]:
    """Return the [system, user] message pair both DeepSeekAdapter and
    the inline adapter in `main.py` feed to /chat/completions."""
    return [
        {"role": "system", "content": NARRATE_DAY_SYSTEM},
        {"role": "user", "content": _build_narrate_day_user_prompt(day, bullets, stats)},
    ]


def parse_narrate_day_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise a parsed JSON object returned by the LLM into the canonical
    rich short-story shape. Backfills `zh`/`en` synopsis from the first
    paragraph of the story so backward-compatible consumers keep working."""
    def _s(k: str) -> str:
        return str(data.get(k, "")).strip()

    proto = data.get("protagonist") if isinstance(data.get("protagonist"), dict) else {}
    supporting_raw = data.get("supporting") if isinstance(data.get("supporting"), list) else []
    supporting: list[dict[str, str]] = []
    for it in supporting_raw[:6]:
        if not isinstance(it, dict):
            continue
        supporting.append({
            "name": str(it.get("name", "")).strip(),
            "name_en": str(it.get("name_en", "")).strip(),
            "role_zh": str(it.get("role_zh", "")).strip(),
            "role_en": str(it.get("role_en", "")).strip(),
        })

    story_zh = _s("story_zh")
    story_en = _s("story_en")

    def _first_para(text: str, cap: int) -> str:
        if not text:
            return ""
        first = text.split("\n\n", 1)[0].strip()
        return first if len(first) <= cap else first[: cap - 1].rstrip() + "…"

    return {
        "title_zh": _s("title_zh"),
        "title_en": _s("title_en"),
        "protagonist": {
            "name": str(proto.get("name", "")).strip(),
            "name_en": str(proto.get("name_en", "")).strip(),
            "why_zh": str(proto.get("why_zh", "")).strip(),
            "why_en": str(proto.get("why_en", "")).strip(),
        },
        "supporting": supporting,
        "story_zh": story_zh,
        "story_en": story_en,
        "tomorrow_zh": _s("tomorrow_zh"),
        "tomorrow_en": _s("tomorrow_en"),
        "zh": _first_para(story_zh, 220),
        "en": _first_para(story_en, 600),
        "degraded": False,
    }


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
        max_tokens: int | None = None,
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
            max_tokens=max_tokens,
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

    async def choose_insert_event(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        if not candidates:
            raise ValueError("choose_insert_event: empty candidates")
        prompt = self._render(
            "choose_insert_event.j2",
            gap_minutes=gap_minutes,
            persona=persona,
            memories=memories,
            candidates=candidates,
            context=context or {},
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"choose_insert_event: expected object, got {type(data).__name__}")
        eid = data.get("id")
        rationale = str(data.get("rationale", "")).strip() or "(no rationale)"
        valid_ids = {c["id"] for c in candidates}
        if eid not in valid_ids:
            raise ValueError(
                f"choose_insert_event: returned id {eid!r} not in candidates {sorted(valid_ids)}"
            )
        return eid, rationale

    async def describe_insert_event(self, event: dict[str, Any]) -> dict[str, str]:
        prompt = self._render(
            "describe_insert_event.j2",
            role=event.get("role", "student"),
            start_name=event.get("start_name", "?"),
            end_name=event.get("end_name", "?"),
            duration_minutes=event.get("duration_minutes", 0),
            tags=event.get("tags", []),
            drives=event.get("drives", {}),
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"describe_insert_event: expected object, got {type(data).__name__}")
        zh = str(data.get("description_zh", "")).strip()
        en = str(data.get("description_en", "")).strip()
        if not zh:
            raise ValueError("describe_insert_event: empty description_zh")
        return {"description_zh": zh, "description_en": en or zh}

    async def describe_activity(
        self,
        persona: dict[str, Any],
        activity: str,
        situation: dict[str, Any],
    ) -> dict[str, str]:
        prompt = self._render(
            "describe_activity.j2",
            persona=persona,
            activity=activity,
            situation=situation,
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"describe_activity: expected object, got {type(data).__name__}")
        zh = str(data.get("description_zh", "")).strip()
        en = str(data.get("description_en", "")).strip()
        if not zh:
            raise ValueError("describe_activity: empty description_zh")
        return {"description_zh": zh, "description_en": en or zh}

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
        messages = build_narrate_day_messages(day, bullets, stats)
        payload = await self.client.chat(
            messages=messages,
            temperature=0.85,
            json_mode=True,
            max_tokens=8000,
        )
        out = self.client.extract_text(payload)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"narrate_day: expected object, got {type(data).__name__}")
        return parse_narrate_day_response(data)

    async def choose_dialog_target(
        self,
        speaker: dict[str, Any],
        candidates: list[dict[str, Any]],
        situation: dict[str, Any],
    ) -> tuple[str | None, str]:
        if not candidates:
            return None, "no candidates"
        prompt = self._render(
            "choose_dialog_target.j2",
            speaker=speaker,
            candidates=candidates,
            situation=situation,
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(
                f"choose_dialog_target: expected object, got {type(data).__name__}"
            )
        tid = data.get("id")
        rationale = str(data.get("rationale", "")).strip() or "(no rationale)"
        # `null` / "none" / "" → stay silent.
        if tid in (None, "", "none", "null", "None"):
            return None, rationale
        valid_ids = {c["id"] for c in candidates}
        if tid not in valid_ids:
            raise ValueError(
                f"choose_dialog_target: id {tid!r} not in candidates {sorted(valid_ids)}"
            )
        return tid, rationale

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

    async def generate_mutter(
        self,
        speaker: dict[str, Any],
        situation: dict[str, Any],
        memories: list[str],
    ) -> dict[str, Any]:
        prompt = self._render(
            "generate_mutter.j2",
            speaker=speaker,
            situation=situation,
            memories=memories,
        )
        out = await self._chat_text(prompt, json_mode=True)
        data = _parse_json_object(out)
        if not isinstance(data, dict):
            raise ValueError(f"generate_mutter: expected object, got {type(data).__name__}")
        line = str(data.get("line", "")).strip()
        if not line:
            raise ValueError("generate_mutter: empty line")
        return {
            "line": line,
            "line_en": str(data.get("line_en", "")).strip() or line,
            "mood": str(data.get("mood", "neutral")).strip() or "neutral",
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

    async def choose_insert_event(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        async def _primary() -> tuple[str, str]:
            return await self.primary.choose_insert_event(
                gap_minutes, persona, memories, candidates, context=context,
            )

        async def _fallback() -> tuple[str, str]:
            return await self.fallback.choose_insert_event(
                gap_minutes, persona, memories, candidates, context=context,
            )

        result, degraded = await safe_call(_primary, _fallback)
        self._record("choose_insert_event", degraded)
        return result

    async def describe_insert_event(self, event: dict[str, Any]) -> dict[str, str]:
        async def _primary() -> dict[str, str]:
            return await self.primary.describe_insert_event(event)

        async def _fallback() -> dict[str, str]:
            return await self.fallback.describe_insert_event(event)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("describe_insert_event", degraded)
        return result

    async def describe_activity(
        self,
        persona: dict[str, Any],
        activity: str,
        situation: dict[str, Any],
    ) -> dict[str, str]:
        async def _primary() -> dict[str, str]:
            return await self.primary.describe_activity(persona, activity, situation)

        async def _fallback() -> dict[str, str]:
            return await self.fallback.describe_activity(persona, activity, situation)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("describe_activity", degraded)
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

    async def choose_dialog_target(
        self,
        speaker: dict[str, Any],
        candidates: list[dict[str, Any]],
        situation: dict[str, Any],
    ) -> tuple[str | None, str]:
        async def _primary() -> tuple[str | None, str]:
            return await self.primary.choose_dialog_target(speaker, candidates, situation)

        async def _fallback() -> tuple[str | None, str]:
            return await self.fallback.choose_dialog_target(speaker, candidates, situation)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("choose_dialog_target", degraded)
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

    async def generate_mutter(
        self,
        speaker: dict[str, Any],
        situation: dict[str, Any],
        memories: list[str],
    ) -> dict[str, Any]:
        async def _primary() -> dict[str, Any]:
            return await self.primary.generate_mutter(speaker, situation, memories)

        async def _fallback() -> dict[str, Any]:
            return await self.fallback.generate_mutter(speaker, situation, memories)

        result, degraded = await safe_call(_primary, _fallback)
        self._record("generate_mutter", degraded)
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
