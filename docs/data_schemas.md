# 数据 Schema 速查

所有 JSON 由 `backend/app/config/schemas.py`（pydantic v2）校验。

## scenes/*.json

```json
{
  "rooms": [
    {
      "index": 0,
      "uid": "a7934434",
      "name": "Kitchen",
      "tag": ["daily life"],
      "adjacent": ["438038e3"],
      "description": "...",
      "position": [79.6, 9.6, 0],
      "containment": 10,
      "furniture": [{"name": "trolley", "num": 2}]
    }
  ]
}
```

> `position[2]` 解释为楼层 z 轴，用于推导 children / siblings。

## personas/<npc_id>.json

```json
{
  "id": "demo_alice",
  "name": "Alice",
  "role": "undergraduate",
  "personality": { "openness": 0.7, "conscientiousness": 0.8, ... },
  "preferences": {
    "favorite_locations": ["64a9bc35"],
    "favorite_tags": ["study"]
  },
  "relations": { "demo_bob": "labmate" },
  "initial_location_uid": "438038e3",
  "schedule_template_id": "demo_alice"
}
```

## schedule_templates/<npc_id>.json

```json
{
  "id": "demo_alice",
  "description": "...",
  "week": {
    "monday": [
      { "start": "08:00", "end": "10:00", "activity": "attend_class", "location_uid": "4d7a7e81" }
    ]
  }
}
```

> 模板仅定义关键时段；空隙留给运行时填充。

## schedule_fragments/fragments.json

```json
{
  "fragments": [
    {
      "id": "frag_chat_cafe",
      "label": "去咖啡角和朋友闲聊",
      "duration_minutes": 15,
      "tags": ["social", "leisure"],
      "preferred_location_uids": ["a62839dd"],
      "cost": 1,
      "preconditions": { "min_energy": 1 }
    }
  ]
}
```

## actions/actions.json

```json
{
  "actions": [
    {
      "id": "move",
      "label": "move(target_uid)",
      "cost": 2,
      "duration_minutes": 5,
      "params": ["target_uid"],
      "preconditions": {
        "agent.location_uid": "!= target_uid",
        "agent.energy": ">= 1"
      },
      "effects": {
        "agent.location_uid": "= target_uid",
        "agent.energy": "-= 1"
      },
      "concurrent_with": ["phone_call"],
      "stochastic": null
    }
  ]
}
```

> 操作符方言：`=` 赋值；`+=` / `-=` 增减；`==` / `!=` / `>=` / `<=` / `>` / `<` 用作 precondition 比较。
> 路径方言：`agent.*` 指执行者；`target.*` 指目标 agent；`item.*` 指目标物品。
