# SIGSAgent Backend

FastAPI 服务，承载场景模块（WorldState 真源）与 Agent 模块（记忆 / 日程 / 决策 / 行为 / 感知）。

## 安装与运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
# 或：pip install -r requirements.txt

# 启动开发服务（默认 http://127.0.0.1:8000）
uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs 可看 OpenAPI 文档。

## 关键路径

| 路径 | 用途 |
|---|---|
| `GET /api/scene/graph` | 场景拓扑图（供前端 SceneGraphView） |
| `GET /api/world` | 实时 WorldState 快照 |
| `GET /api/agents/{id}/memory` | STM / LTM / 三元组图（含 `text_en` 双语字段） |
| `GET /api/agents/{id}/schedule` | 5min 槽位时间轴 |
| `GET /api/agents/{id}/history` | 行为历史（GOAP 已执行步骤） |
| `GET /api/sim/status` | `{running, sim_time, pause_reason, current_day}` |
| `GET /api/sim/day_summaries` | 历次跨午夜的双语旁白 |
| `POST /api/sim/start` / `pause` / `step` | 启动 / 恢复（开启下一天）/ 暂停 / 单步 |
| `WS /ws` | `welcome` `tick` `agent_decision` `behavior` `dialog` **`day_summary`** `agent_error` |

## 关键能力

- **跨午夜自动旁白**：`sim/loop.py` 检测 sim 跨日，收集 dialog/behavior，
  调 LLM `narrate_day` 产中英双语段落，自动 `pause` 并推 `day_summary` 事件。
- **行为反馈写回 STM**：每条原子动作执行后写一条"结果型"STM，含
  `ok / note / pre_state / post_state`，决策可读。
- **双语记忆**：`ShortTermItem` / `LongTermItem` 都带 `text_en`；
  `summarize_memories` / `generate_dialog` / `narrate_day` prompt 强制双语 JSON。
- **LLM 容错**：`SafeLLMAdapter(primary, fallback)`，失败标记 `degraded=True`。

## 模块图

```
api/      <- REST + WebSocket 入口
sim/      <- 5min tick 主循环
agents/   <- NPCAgent 聚合（perception/memory/schedule/decision/behavior）
world/    <- 场景图 + 全局 WorldState
llm/      <- OpenAI 兼容客户端 + Mock 兜底
config/   <- pydantic 校验 + 加载 data/
events/   <- 内部事件总线 -> WS 广播
persistence/  <- SQLite
```

## 测试

```powershell
pytest
```
