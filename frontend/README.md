# SIGSAgent Frontend

Vue 3 + Vite + TypeScript + vis-network + Pinia。

## 安装与运行

```powershell
npm install
npm run dev
```

Vite 默认监听 `127.0.0.1:5173`，并把 `/api` 和 `/ws` 代理到后端 `127.0.0.1:8000`。

## 页面

| 路径 | 文件 | 用途 |
|---|---|---|
| `/relations` | `views/RelationView.vue` | 人际关系网（参考 校园人设关系网示意_bilingual.html） |
| `/scene` | `views/SceneGraphView.vue` | 场景拓扑图（基于 guoyi_rooms_v2.json） |
| `/agent` | `views/AgentDetailView.vue` | 单 NPC 的记忆 / 日程 / 行为 / 感知 |
| `/memory-graph` | `views/MemoryGraphView.vue` | 记忆三元组叙事图 |
| `/timeline` | `views/TimelineView.vue` | WebSocket 事件流 |

可复用组件：`NetworkGraph.vue`（vis-network 通用封装）、`MemoryPanel.vue`、`SchedulePanel.vue`、`BehaviorHistory.vue`、`PerceptionPanel.vue`。
