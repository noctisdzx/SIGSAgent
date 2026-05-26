"""Direct STM->LTM compression smoke against the live DeepSeek API.

Stands up the same components the backend uses (LLM adapter + STM + LTM +
MemoryCompressor) but in isolation. Stuffs 30 synthetic short-term memories
of demo_alice, then awaits MemoryCompressor.maybe_compress() — which sends
a real prompt to DeepSeek and parses the JSON response into one new LTM
record. Prints before/after counts AND the literal Chinese sentence the
LLM produced.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.agents.memory.compressor import MemoryCompressor  # noqa: E402
from app.agents.memory.long_term import LongTermMemory     # noqa: E402
from app.agents.memory.short_term import ShortTermItem, ShortTermMemory  # noqa: E402
from app.llm.adapter import build_llm_adapter             # noqa: E402
from app.settings import get_settings                     # noqa: E402


SAMPLES = [
    "起床洗漱，准备开始新的一天",
    "在食堂吃早餐，遇见室友打招呼",
    "走去教学楼上专业课，路上遇到同班同学",
    "上午第一节高等数学课，老师讲极限",
    "课间和同桌讨论刚才的难题",
    "继续听第二节专业课，做了两页笔记",
    "课后去图书馆借了两本参考书",
    "在图书馆刷了一组习题",
    "午餐在二食堂吃了麻辣香锅",
    "饭后在校园里散步消食",
    "回宿舍午休 30 分钟",
    "下午去实验室做了一组实验",
    "实验中和搭档争论实验步骤",
    "完成实验记录，整理仪器",
    "下午茶时间去咖啡厅喝拿铁",
    "在咖啡厅碰到学长聊了未来规划",
    "去操场跑了 3 公里",
    "运动完拉伸 10 分钟",
    "回宿舍冲澡换衣服",
    "晚餐去食堂吃了番茄牛腩面",
    "晚上参加社团例会讨论下周活动",
    "和社团朋友约了周末爬山",
    "回宿舍写一份社团策划",
    "复习今天的高等数学笔记",
    "看了一集英文纪录片练听力",
    "在群里和高中朋友聊近况",
    "整理桌面，规划明天的待办",
    "刷牙洗脸准备睡觉",
    "躺床上看了 20 分钟课外书",
    "关灯入睡",
]


async def main() -> int:
    settings = get_settings()
    print(f"LLM: base_url={settings.llm_base_url}  model={settings.llm_model}")
    if not settings.llm_api_key or settings.llm_api_key.startswith("sk-xxx"):
        print("!! LLM_API_KEY missing — abort", file=sys.stderr)
        return 1

    llm = build_llm_adapter()
    print(f"adapter: {type(llm).__name__}")

    stm = ShortTermMemory(capacity=30)
    ltm = LongTermMemory(capacity=15)
    base_ts = datetime(2026, 5, 26, 8, 0)
    for i, text in enumerate(SAMPLES):
        stm.add(ShortTermItem(
            id=f"smoke_{i}_{uuid.uuid4().hex[:6]}",
            text=text,
            ts=base_ts + timedelta(minutes=5 * i),
            source="schedule",
            hit_count=i % 5,  # vary hits so sort order is interesting
            meta={},
        ))

    print(f"\nBEFORE  STM={len(stm.all())}  LTM={len(ltm.all())}")
    print(f"        top STM by hits (first 3):")
    for it in sorted(stm.all(), key=lambda x: (-x.hit_count, -x.ts.timestamp()))[:3]:
        print(f"          hits={it.hit_count}  {it.text!r}")

    # Push one more STM beyond capacity — but here STM already at 30 so the
    # compressor's trigger predicate (len>=cap) fires; force it with `force=True`.
    compressor = MemoryCompressor(stm, ltm, llm)
    print("\nrunning MemoryCompressor.compress() (forced) ...")
    t0 = datetime.now()
    result = await compressor.compress()
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"...returned in {elapsed:.2f}s -> {result!r}")

    print(f"\nAFTER   STM={len(stm.all())}  LTM={len(ltm.all())}")

    if ltm.all():
        new_ltm = ltm.all()[-1]
        out_path = Path(__file__).resolve().parent / "_llm_compression_result.json"
        import json
        out_path.write_text(json.dumps({
            "id": new_ltm.id,
            "text": new_ltm.text,
            "source_ids": new_ltm.source_ids,
            "degraded": new_ltm.degraded,
            "meta": new_ltm.meta,
            "elapsed_seconds": elapsed,
            "before_stm": 30,
            "after_stm": len(stm.all()),
            "after_ltm": len(ltm.all()),
            "remaining_stm_texts": [it.text for it in stm.all()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nNEW LTM written to: {out_path}")
        print(f"  id        : {new_ltm.id}")
        print(f"  degraded  : {new_ltm.degraded}  <-- False = real LLM, True = fallback")
        print(f"  source_ids: {len(new_ltm.source_ids)} items")
        print(f"  (LLM text saved to JSON; read it from there to avoid console codepage issues)")

        if new_ltm.degraded:
            print("\n!! result was DEGRADED — DeepSeek call failed and fallback ran")
            return 2
        else:
            print("\nOK: STM->LTM compression succeeded via REAL DeepSeek call")
            return 0
    else:
        print("!! no new LTM produced", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
