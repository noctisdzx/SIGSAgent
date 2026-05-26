"""End-to-end DeepSeek LLM smoke test.

Runs against a live backend at http://127.0.0.1:8000. Polls the REST API,
counts what really happened (per-agent STM/LTM/graph + fragment-fill +
behavior history + degraded-flag distribution) and prints a sample of
real LLM-generated content (an LTM compression line and a fragment choice).

It also tails the backend's own log file when present to count how many
DeepSeek HTTP calls have hit the live endpoint.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:8000"
LOG_FILE = Path(r"C:\Users\2023.04\.cursor\projects\f-SIGSAgent\terminals\521458.txt")


def get(path: str, **q) -> object:
    url = f"{BASE}{path}"
    if q:
        url += "?" + urlencode(q)
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def count_deepseek_calls() -> int:
    if not LOG_FILE.exists():
        return -1
    text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"deepseek\.com/v1/chat/completions", text))


def main() -> int:
    print("== 1. health ==")
    h = get("/api/health")
    print(json.dumps(h, ensure_ascii=False))
    if not h.get("sim_running"):
        print("!! sim not running — abort", file=sys.stderr)
        return 1

    print("\n== 2. wait 20s while sim ticks + slot_filler/compressor calls LLM ==")
    start_calls = count_deepseek_calls()
    print(f"   deepseek calls before wait: {start_calls}")
    time.sleep(20)
    end_calls = count_deepseek_calls()
    print(f"   deepseek calls after  wait: {end_calls}")
    if end_calls >= 0:
        print(f"   delta during 20s:          {end_calls - start_calls}")

    print("\n== 3. per-agent state ==")
    agents = get("/api/agents")
    print(f"   total agents: {len(agents)}")

    stm_total = ltm_total = graph_total = hist_total = 0
    ltm_real = ltm_degraded = 0
    fragment_slot_agents = 0
    template_slot_agents = 0
    agents_with_ltm: list[tuple[str, int]] = []
    agents_with_history: list[tuple[str, int]] = []

    sample_ltm: dict | None = None
    sample_fragment: dict | None = None
    sample_agent: str | None = None
    sample_target_state: dict | None = None

    # Inspect every agent.
    for a in agents:
        aid = a["id"]
        try:
            mem = get(f"/api/agents/{aid}/memory")
            sch = get(f"/api/agents/{aid}/schedule")
            hist = get(f"/api/agents/{aid}/history", limit=200)
        except Exception as exc:
            print(f"   !! {aid}: {exc}")
            continue

        stm = mem.get("short_term", [])
        ltm = mem.get("long_term", [])
        graph = mem.get("graph", [])
        slots = sch.get("slots", [])

        stm_total += len(stm)
        ltm_total += len(ltm)
        graph_total += len(graph)
        hist_total += len(hist)

        for item in ltm:
            if item.get("degraded"):
                ltm_degraded += 1
            else:
                ltm_real += 1
                if sample_ltm is None and not item.get("meta", {}).get("seed"):
                    sample_ltm = {"agent": aid, **item}

        n_frag = sum(1 for s in slots if s.get("kind") == "fragment")
        n_tpl = sum(1 for s in slots if s.get("kind") == "template")
        if n_frag > 0:
            fragment_slot_agents += 1
            if sample_fragment is None:
                # capture the first fragment-filled slot to display
                frag_slot = next(s for s in slots if s.get("kind") == "fragment")
                sample_fragment = {"agent": aid, **frag_slot}
        if n_tpl > 0:
            template_slot_agents += 1

        # capture a target_state from a template slot for sanity
        if sample_target_state is None:
            for s in slots:
                if s.get("kind") == "template":
                    # schedule_view currently does not expose target_state;
                    # cross-check by reading config directly:
                    sample_target_state = {
                        "agent": aid,
                        "slot": {
                            "index": s.get("index"),
                            "activity": s.get("activity"),
                            "location_uid": s.get("location_uid"),
                            "source_id": s.get("source_id"),
                        },
                    }
                    break

        if ltm:
            agents_with_ltm.append((aid, len(ltm)))
        if hist:
            agents_with_history.append((aid, len(hist)))
        if sample_agent is None and len(hist) >= 3:
            sample_agent = aid

    print()
    print(f"   STM total : {stm_total}")
    print(f"   LTM total : {ltm_total}  (real={ltm_real}, degraded={ltm_degraded})")
    print(f"   Graph     : {graph_total}")
    print(f"   History   : {hist_total} behavior records across {len(agents)} agents")
    print(f"   agents with TEMPLATE slots : {template_slot_agents}/{len(agents)}")
    print(f"   agents with FRAGMENT slots : {fragment_slot_agents}/{len(agents)}  (slot_filler/LLM fired)")
    print(f"   agents with ≥1 LTM         : {len(agents_with_ltm)}")
    print(f"   agents with ≥1 history     : {len(agents_with_history)}")

    print("\n== 4. top 5 agents by behavior history ==")
    top_hist = sorted(agents_with_history, key=lambda x: -x[1])[:5]
    for aid, n in top_hist:
        print(f"   {aid:30s}  {n} actions")

    if sample_ltm is not None:
        print("\n== 5. SAMPLE LTM (LLM-generated, non-seed, non-degraded) ==")
        print(f"   agent     : {sample_ltm['agent']}")
        print(f"   text      : {sample_ltm['text']}")
        print(f"   source_ids: {sample_ltm.get('source_ids')}")
        print(f"   meta      : {sample_ltm.get('meta')}")
    else:
        print("\n== 5. no real LTM yet (compression not triggered for any agent) ==")

    if sample_fragment is not None:
        print("\n== 6. SAMPLE FRAGMENT pick (LLM slot_filler decided) ==")
        print(f"   agent     : {sample_fragment['agent']}")
        print(f"   activity  : {sample_fragment['activity']}")
        print(f"   location  : {sample_fragment['location_uid']}")
        print(f"   source_id : {sample_fragment['source_id']}")
        print(f"   span      : {sample_fragment['start']} - {sample_fragment['end']}")
    else:
        print("\n== 6. no fragment slot filled yet ==")

    if sample_agent is not None:
        print(f"\n== 7. SAMPLE DECISION TRACE  agent={sample_agent} ==")
        hist = get(f"/api/agents/{sample_agent}/history", limit=8)
        for h in hist[-8:]:
            params = h.get("params") or {}
            ok = "OK" if h.get("ok") else "DEGRADED"
            print(f"   [{ok}] {h.get('ts_sim','?')}  {h.get('action_id'):10s}  {params}")

    print("\n== 8. final deepseek call counter ==")
    final_calls = count_deepseek_calls()
    print(f"   total POSTs to deepseek.com observed in backend log: {final_calls}")
    print(f"   (during this 20s window: {final_calls - start_calls if final_calls >= 0 and start_calls >= 0 else 'n/a'})")

    print("\nDONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
