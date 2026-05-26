# SIGSAgent

类斯坦福小镇（Stanford Smallville）风格的校园多智能体仿真项目。

- **后端**：Python + FastAPI，承载场景模块（WorldState 真源）与 Agent 模块（记忆 / 日程 / 决策 / 行为 / 感知）。
- **前端**：Vue 3 + Vite + vis-network，提供人际关系网、场景拓扑、单 NPC 的记忆/日程/行为详情等多页面。
- **通信**：WebSocket 推送 tick 事件，REST 拉取详情与配置。

## 目录速览

```
SIGSAgent/
├── backend/   # FastAPI 仿真服务
├── frontend/  # Vue 3 可视化前端
├── data/      # 共享只读数据（场景 / 人设 / 动作 / 日程模板）
├── runtime/   # 运行时产物（SQLite / 快照 / 日志），可随时清空“重开一局”
├── docs/      # 架构与数据契约文档
└── scripts/   # 启动、初始化、种子脚本
```

## 快速开始

```powershell
# 1) 把根目录场景文件迁入 data/scenes/
python scripts/init_data.py

# 2) 安装并启动后端
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload

# 3) 安装并启动前端
cd ../frontend
npm install
npm run dev
```

或直接运行 `scripts/run_dev.ps1` 一键拉起前后端。

更多说明见 [docs/architecture.md](docs/architecture.md)。
