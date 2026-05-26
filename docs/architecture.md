# 架构总览

SIGSAgent 是一个类斯坦福小镇风格的校园多智能体仿真。下图概括前后端模块、运行时数据流与控制流。

## 顶层

```
┌────────────────────────────┐         REST /api/*           ┌───────────────────────────┐
│  Frontend (Vue 3 + Vite)   │ ───────────────────────────▶  │  Backend (FastAPI)        │
│                            │ ◀────── WS /ws (tick…)  ────  │                           │
└────────────────────────────┘                                └───────────────────────────┘
        │                                                            │
        │ vis-network 多视图                                          │
        ▼                                                            ▼
    Relations / Scene / AgentDetail /                       SimLoop (5min tick) →
    MemoryGraph / Timeline                                  perceive → decide → act
                                                                ▲          │
                                                                │          ▼
                                                          Perception   WorldState (真源)
                                                                │          │
                                                                ▼          ▼
                                                           Memory     SceneGraph
                                                           ├─ STM (30)
                                                           ├─ LTM (15)
                                                           └─ MemoryGraph (三元组)
```

## 一次 tick（5min sim time）

1. `sim/clock.py` 触发 `on_tick`。
2. `sim/loop.py` 推进 `world.sim_time += 5min`。
3. 对每个已注册的 `NPCAgent`：
   1. **Perception**：`children(here) ∪ siblings(here)` → `PerceptionSnapshot`。
   2. **Memory retrieve**：加载全部 STM + 检索 LTM，选 top-5 并 bump 命中数。
   3. **Decision**：
      - 当前是模板时段 → 直接拿到 `activity`；
      - 当前是空隙 → `slot_filler` 选片段（LLM，失败回退）。
   4. **Schedule → STM**：`builder.schedule_item_to_stm()` 写入。
   5. **Memory compress**：若 STM > 30，触发压缩（见 [llm_fallback.md](llm_fallback.md)）。
   6. **GOAP plan**：把活动解析为原子动作链。
   7. **Behavior execute**：第一条原子动作的 `effects` 写回 WorldState，加入 history。
4. `events.bus` 广播本 tick 事件到 WS 订阅者。

## 数据流方向

- **只读**：`data/*.json` → `config.loader` → `config.registry`。
- **可变真源**：`WorldState`。所有动作 effect 写入这里；所有感知从这里读。
- **持久化**：`runtime/memory.db`（STM/LTM/记忆图谱/行为历史）+ `runtime/snapshots/*`。

## 关键不变式

- 决策模块**不**直接读 `MemoryGraph`（仅用于玩家叙事）。
- 感知**不**穿透到孙节点（按你的设定）。
- LLM 调用必须有兜底；失败产物必须 `degraded=True`。
