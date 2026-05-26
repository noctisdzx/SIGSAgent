# SIGSAgent

> 一个类斯坦福小镇（Stanford Smallville）风格的**校园多智能体仿真**项目。
> 60+ 位 NPC 在 16 个房间组成的校园拓扑里依各自的人设与课表生活、移动、对话；
> 每条决策都对接真实 LLM（DeepSeek，OpenAI-compatible），跨午夜会自动生成
> 一段中英双语的"上帝视角旁白"。

![banner](./guoyi_rooms_v2.json)

```
┌─────────────────────────┐   REST /api/*        ┌──────────────────────────────┐
│  Frontend (Vue 3+Vite)  │ ───────────────────▶ │  Backend  (FastAPI + asyncio) │
│                         │ ◀──── WS /ws  ────── │                              │
└─────────────────────────┘                       └──────────────────────────────┘
        │                                                │
        ▼                                                ▼
  Relations / Scene / Memory /                  SimLoop (5 min tick)
  Agent Detail / Timeline / Heatmap            perceive → decide → act
        │                                                │
        ▼                                                ▼
   DaySummaryModal (旁白弹窗)                    WorldState  + SceneGraph
                                                  Memory: STM(30) / LTM(15) / Graph
                                                  LLM Adapter (real + mock fallback)
```

---

## 核心特性

### 仿真引擎
- **5 分钟粒度 tick**：`sim_tick_seconds=300`，单 tick 实际间隔可调（默认 1s 加速）。
- **WorldState 真源**：所有动作的 `effects` 写回 WorldState，所有 perception 从这里读。
- **跨午夜自动旁白**：sim 跨过 00:00 时自动收集当天 dialog + behavior，喂给 LLM 生成
  中英双语段落，落 `sim.day_summaries`、广播 `day_summary` WS 事件，并自动 **pause** ——
  玩家点「▶ 开启下一天」才继续。

### Agent 架构
- **Perception**：`children(here) ∪ siblings(here)`，不穿透到孙节点。
- **Memory**
  - **STM**（30 槽，命中计数）
  - **LTM**（15 槽，命中计数；STM 溢出→LLM 压缩；LTM 不足 5 槽时先压缩末尾 3 条让位）
  - **Memory Graph**（三元组，仅供旁白与玩家叙事，决策不读）
  - 全部记忆**双语存储**（`text` / `text_en`），UI 一键切换语言。
- **Schedule**
  - 周课表式模板（每天不同），关键时段锚定，留大量空隙
  - 18 条通用 fragments，由 LLM `choose_fragment` 在空隙处插值
  - 每个落地的 schedule item 即一条 STM
- **Decision = SlotFiller + GOAP**
  - SlotFiller：把当前 perception/memory/lastActivity 作为 context 喂 LLM
  - GOAP：基于 `actions.json` 的 preconditions/effects/cost A\* 求解；支持 `>=, <=` 等比较算子
- **Behavior**：6 个原子动作（move / talk / interact / sleep / wake_up / idle），
  执行后将 `pre_state → post_state`、`ok`、`note` 一并写回 STM 与 WS。

### 对话
- 社交活动 + 同房间他人时触发 `_maybe_have_dialog`
- LLM 输出双语 `speaker_line / listener_line / topic / tone`
- 双方 STM 各自记录一条带游戏时间戳的中文 + 英文版本
- Memory Graph 加 `said_to / heard_from` 三元组
- WS 广播 `dialog` 事件，前端 TimelineFeed 直接渲染

### LLM 容错
所有 LLM 调用走 `SafeLLMAdapter(primary, fallback)`：先调真实 API（DeepSeek），
失败回退到 `MockLLMAdapter`，并把 `degraded=True` 一路传播到产物上。

### 前端可视化（Vue 3 + vis-network + Pinia）
| 路由 | 内容 |
|---|---|
| `/relations` | 60 NPC 社交关系图 + 5 标签侧栏（NPC/Edge/Scenes/Timeline/Heat） |
| `/scene` | 16 房间拓扑 + 实时 NPC 追踪 + **房间人数热力图** + 房间详情 |
| `/agent/:id` | 单 NPC 的 STM/LTM/Schedule/Behavior/Perception |
| `/memory-graph` | 全 NPC 三元组叙事图（已把 `npcNN_xxx` 解析为人名） |
| `/timeline` | 实时 WS 事件流 + 种子叙事轴 |

顶部条始终展示 **⏱ 当前 sim 时间 / Pause / Resume / Next-day / 📜 Recap**；
跨午夜时弹出全屏的旁白 Modal。中/EN 一键互换。

---

## 目录结构

```
SIGSAgent/
├── backend/                FastAPI 服务（uvicorn app.main:app）
│   └── app/
│       ├── api/            REST + WebSocket 入口
│       ├── sim/            5min tick 主循环 + 旁白触发器
│       ├── agents/         NPCAgent + memory/schedule/decision/behavior/perception
│       ├── world/          SceneGraph + WorldState
│       ├── llm/            OpenAI-compatible client + prompts/*.j2
│       ├── config/         pydantic 校验 + data/ 加载
│       ├── events/         内部事件总线 → WS 广播
│       └── persistence/    aiosqlite
├── frontend/               Vue 3 + Vite 前端
│   └── src/
│       ├── views/          路由级页面
│       ├── components/     可复用面板（DaySummaryModal / RoomHeatPanel / …）
│       ├── stores/         Pinia stores（lang / events / world / sim / agents / …）
│       └── api/            REST 端点 + WS 客户端
├── data/                   共享只读剧本（场景 / 60 personas / 60 schedule_templates / actions / fragments）
├── runtime/                运行时产物（SQLite / 快照），可随时清空"重开一局"
├── docs/                   架构 / 模块 / 数据契约 / LLM 兜底 / UX spec
├── scripts/                启动 / 重置 / 重生成 / e2e 烟雾测试
├── .env.example            环境变量模板
└── guoyi_rooms_v2.json     原始场景拓扑（已被 scenes/ 消费）
```

---

## 快速开始

### 0. 准备 Python ≥ 3.11 与 Node.js ≥ 18

### 1. 配置环境变量

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入你的 DeepSeek key（或任意 OpenAI-compatible endpoint）
```

`.env` 关键项：

| Key | 默认 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-兼容 endpoint |
| `LLM_API_KEY` | — | 填你的 key |
| `LLM_MODEL` | `deepseek-chat` | |
| `SIM_TICK_SECONDS` | `300` | sim-world 一个 tick 多少秒 |
| `SIM_REAL_TICK_SECONDS` | `1` | 真实世界两个 tick 间隔（越小越快） |
| `SIM_AUTOSTART` | `false` | 后端启动后是否自动开始 tick |
| `SIM_START_TIME` | `2026-05-26T07:00:00` | sim 起始时间；改成 `…T23:55:00` 可立刻验证跨午夜 |

### 2. 一键拉起（PowerShell）

```powershell
.\scripts\run_dev.ps1
```

会在两个独立终端里分别跑 backend（:8000）和 frontend（:5173 或 :5174）。

或手动启动：

```powershell
# 后端
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn app.main:app --reload

# 前端
cd ..\frontend
npm install
npm run dev
```

打开 **http://127.0.0.1:5173/** 即可。
API 文档在 **http://127.0.0.1:8000/docs**。

### 3. 想立刻看跨日旁白？

```powershell
$env:SIM_START_TIME = "2026-05-26T23:55:00"
uvicorn app.main:app --reload
```

第一个 tick 就会跨日，自动暂停 + 弹出旁白 Modal。

---

## 关键 API

### REST

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | 存活探针 |
| GET | `/api/scene/graph` | 场景拓扑（vis-network 格式） |
| GET | `/api/world` | 实时 WorldState 快照 |
| GET | `/api/agents` | 60 NPC 简表 |
| GET | `/api/agents/{id}` | 单 NPC 完整 persona |
| GET | `/api/agents/{id}/memory` | STM / LTM / 三元组（均含 `text_en`） |
| GET | `/api/agents/{id}/schedule` | 5min 槽位时间轴 |
| GET | `/api/agents/{id}/history` | GOAP 已执行步骤 |
| GET | `/api/agents/{id}/perception` | 当前 perception 快照 |
| GET | `/api/relations` | 123 条关系边 |
| GET | `/api/scenes-library` | 37 个剧本场景 |
| GET | `/api/timeline-seed` | 35 条种子叙事 |
| **GET** | **`/api/sim/status`** | `{running, sim_time, pause_reason, current_day}` |
| **GET** | **`/api/sim/day_summaries`** | 历史旁白列表（双语） |
| POST | `/api/sim/start` | 启动 / 恢复（=「开启下一天」） |
| POST | `/api/sim/pause` | 暂停 |
| POST | `/api/sim/step` | 单 tick 步进 |
| POST | `/api/config/reload` | 热重载 `data/*` |

### WebSocket `/ws`

订阅方收到的事件类型：

| `type` | 含义 |
|---|---|
| `welcome` | 握手 + 当前 WorldState 快照 |
| `tick` | 每个 tick 推一次，含 `world_delta.moved` 与 `recent_decisions` |
| `agent_decision` | 单 NPC 决定/执行动作时 |
| `behavior` | 动作执行结果（含 `pre_state` / `post_state`） |
| `dialog` | NPC 对话（中英双语 lines + topic + tone） |
| `day_summary` | **跨午夜旁白**：`{day, narrative_zh, narrative_en, stats, degraded}` |
| `agent_error` | 单 NPC tick 失败 |

---

## 数据契约速览

| 目录 | 内容 |
|---|---|
| `data/scenes/` | 场景拓扑图（房间 + adjacent 邻接） |
| `data/personas/` | 单 NPC 人格（性格 / 偏好 / 关系 / 初始位置） |
| `data/schedule_templates/` | 每个 NPC **每天不同**的周课表，每个 slot 含 `target_state` |
| `data/schedule_fragments/fragments.json` | 18 条通用片段，duration 5–45 分钟 |
| `data/actions/` | 6 个 GOAP 动作（preconditions / effects / cost） |
| `data/relations.json` | 123 条关系边 |
| `data/scenes_library.json` | 37 个剧本场景 |
| `data/timeline_seed.json` | 35 条种子叙事 |
| `data/memory_seed.json` | 每个 NPC 启动时预置的 STM/LTM/triplet |

热改之后调 `POST /api/config/reload`，无需重启。

---

## 维护脚本

| 脚本 | 作用 |
|---|---|
| `scripts/init_data.py` | 把根目录的 `guoyi_rooms_v2.json` 迁入 `data/scenes/` |
| `scripts/seed_demo_npcs.py` | 生成最小可跑通的 demo NPC 集 |
| `scripts/regenerate_schedules.py` | **重新生成 60 份周课表**：稀疏锚点 + 凌晨睡眠守卫 + 留给 LLM 大量空隙 |
| `scripts/reset_runtime.ps1` | 清空 `runtime/`（SQLite + 快照）后"重开一局" |
| `scripts/e2e_llm_smoke.py` | 直接打 DeepSeek 跑通 `choose_fragment / summarize / triplet / dialog / narrate_day` |
| `scripts/e2e_llm_compression.py` | STM→LTM 压缩流程的端到端验证 |

---

## 测试

```powershell
cd backend
pytest -q              # 82 passing
```

包括场景图、WorldState、STM/LTM、记忆图谱、schedule 时间轴、SlotFiller、GOAP planner、
behavior executor、感知、tick、LLM fallback。

---

## 延伸阅读

- [docs/architecture.md](docs/architecture.md) — 一次 tick 的完整数据流
- [docs/modules.md](docs/modules.md) — 各 backend 模块责任边界
- [docs/data_schemas.md](docs/data_schemas.md) — JSON 契约逐字段说明
- [docs/llm_fallback.md](docs/llm_fallback.md) — LLM 容错协议
- [docs/reference_ux_spec.md](docs/reference_ux_spec.md) — 前端视觉规范（色板、热力 ramp、布局栅格）

---

## 路线图

- [ ] `SimLoop._tick` 内 61 个 agent 并发（`asyncio.gather`）以解锁高速跨日测试
- [ ] DaySummaryModal 支持翻看历史旁白与"本周回顾"
- [ ] 把 `actions.json` 扩到 ~12 条原子动作，让 GOAP 搜索空间更丰富
- [ ] 给 Memory Graph 三元组的 `predicate` 也输出双语
- [ ] Persistence：把当前以内存为主的 STM/LTM/Graph 全量落 SQLite，支持断点续跑

---

## License

MIT。`data/` 里的中文人设与剧本为本项目原创，欢迎在保留署名前提下取用做研究/Demo。
