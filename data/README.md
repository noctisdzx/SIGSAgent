# `data/` — 共享只读剧本

所有运行所需的"剧本类"配置都放在这里，由后端 `app/config/loader.py` 统一加载并用 pydantic 校验。

| 子目录 | 内容 | 由谁消费 |
|---|---|---|
| `scenes/` | 场景拓扑图（房间 + adjacent 邻接） | `app/world/scene_graph.py` |
| `personas/` | 单个 NPC 的人格配置（性格 / 偏好 / 关系 / 初始位置） | `app/agents/agent.py` |
| `schedule_templates/` | 单个 NPC 的周课表式日程模板（按 1h/2h 关键时段） | `app/agents/schedule/template.py` |
| `schedule_fragments/` | 通用日程片段池（5min 起步，含 tag、cost、preferred_loc） | `app/agents/schedule/fragments.py` |
| `actions/` | GOAP 动作库（preconditions / effects / cost） | `app/agents/behavior/action_specs.py` |

> 修改后调用 `POST /api/config/reload` 即可热重载（loader 支持）。
