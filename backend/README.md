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
| `GET /api/agents/{id}/memory` | STM / LTM / 三元组图 |
| `GET /api/agents/{id}/schedule` | 5min 槽位时间轴 |
| `GET /api/agents/{id}/history` | 行为历史（GOAP 已执行步骤） |
| `WS /ws` | tick / agent_decision / memory_update 等事件流 |

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
