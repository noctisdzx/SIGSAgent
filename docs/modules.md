# 模块职责与接口契约

## 后端模块树

```
backend/app/
├── world/        场景模块（WorldState 真源）
├── agents/
│   ├── memory/        STM / LTM / MemoryGraph / Retriever / Compressor / Store
│   ├── schedule/      Template / Fragments / Timeline / Builder
│   ├── decision/      SlotFiller (LLM) / GoapPlanner (A*)
│   ├── behavior/      ActionSpecLibrary / BehaviorExecutor
│   └── perception/    Perceiver (children + siblings)
├── llm/           OpenAI-兼容 Client / Adapter / Mock 兜底 / Retry / Prompts
├── config/        pydantic schemas / loader / registry
├── sim/           TickClock / SimLoop
├── events/        EventBus -> WS 广播
└── persistence/   SQLite
```

## 关键契约

### 场景模块 `world/`

- `SceneGraph.children(uid)`：当前节点 adjacent 中、`position[2]` **更低** 的节点。
- `SceneGraph.siblings(uid)`：当前节点 adjacent 中、`position[2]` **相等** 的节点。
- `WorldState` 是 effect 的唯一写入目标；`snapshot()` 给前端 REST。

### 记忆模块 `agents/memory/`

| 项 | 容量 | 排序键（用于压缩 & 优先级） |
|---|---|---|
| STM | 30 | `hit_count desc, ts desc`（新鲜优先） |
| LTM | 15 | `hit_count desc, ts desc` |

- **检索**：`retriever.retrieve(query, top_k=5)`；命中即 `bump_hit`。
- **压缩**：见 [llm_fallback.md](llm_fallback.md) 的三段式策略。

### 日程模块 `agents/schedule/`

- 模板 = 周课表式 JSON，仅定义关键时段（1h/2h）。
- 片段 = 通用 5min 起步活动池，由 `decision/slot_filler.py` 在 timeline 空隙中插入。
- **每条**已确定槽位 → 通过 `builder.schedule_item_to_stm()` 写一条 STM。

### 决策模块 `agents/decision/`

- `SlotFiller`：LLM 选片段 → 失败回退到按 persona favorite_tags 加权随机。
- `GoapPlanner`：A*；对应参考 HTML 第 ~1583 行的 JS 实现。

### 行为模块 `agents/behavior/`

- `actions.json` 的 `preconditions`/`effects` 采用字符串 mini-DSL：
  `"agent.energy": ">= 1"`、`"agent.location_uid": "= target_uid"`。
- 执行时由 `executor.py` 解析并写回 WorldState。

### 感知模块 `agents/perception/`

- 唯一公开方法 `perceive(agent_id, world) -> PerceptionSnapshot`。
- 视野严格 = children + siblings（不含 grandchildren）。

### 配置模块 `config/`

- 全部 JSON 经 pydantic 校验后进入 `Registry`。
- `/api/config/reload` 触发 `ConfigLoader.load_*` 重读 + 替换。

## 前端组件 → 后端端点 对照

| 前端 | 后端 |
|---|---|
| `RelationView.vue` | `GET /api/agents` |
| `SceneGraphView.vue` | `GET /api/scene/graph` |
| `AgentDetailView.vue` | `GET /api/agents/{id}/memory`、`/schedule`、`/history`、`/perception` |
| `MemoryGraphView.vue` | `GET /api/agents/{id}/memory`（`graph` 字段） |
| `TimelineView.vue` | `WS /ws`（事件流） |
