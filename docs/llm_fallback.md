# LLM 调用与兜底策略

记忆系统是 LLM 调用大户（每次 STM 压缩 / LTM 压缩 / 三元组抽取 / 片段选择都会触发）。任何一次抖动都不能让仿真停摆——以下是统一兜底策略。

## 三段式

```
  primary (real LLM, OpenAI compat)
  ├─ ok       → 返回结果，degraded = False
  └─ throw    → tenacity 重试 LLM_MAX_RETRIES 次
        ├─ ok    → 返回结果
        └─ throw → fallback (MockLLMAdapter)
                  → 返回结果，degraded = True
```

实现位置：`backend/app/llm/retry.py:with_fallback(primary, fallback)`。

## 各调用点的 fallback 行为

| 调用点 | 失败时的兜底 |
|---|---|
| `MemoryCompressor._llm_compress_stm` | 用 `" \| "` 拼接源条目文本，`degraded=True` |
| `MemoryCompressor._llm_compress_ltm` | 同上 |
| `SlotFiller.fill` | 在 fitting fragments 上按 `persona.favorite_tags` 加权随机 |
| `extract_triplets` | 模板化为 `(agent, "did", event[:30])` |

## STM ↔ LTM 压缩规则（来自需求）

1. STM 超过 30 → 触发压缩。
2. 若 `LTM.free_slots() >= 5`：
   - 取 STM 中 `hit_count` 前 10（同分按时间倒序）压成 1 条 LTM；
   - 丢弃 STM 中后 20 条（即剩余里最低优先级的 20）。
3. 若 `LTM.free_slots() < 5`：
   - 先把 LTM 中 `hit_count` 后 3 压成 1 条腾位；
   - 再执行第 2 步。
4. 所有 fallback 产物 `degraded=True`，前端以红色 badge 标记，便于排查。

## 限速与并发

- 每 NPC 每 tick 至多 1 次 LLM 调用（决策时段，且仅在空隙）。
- 压缩调用走单独的 task pool，不阻塞 tick 主线（在后续实现中接入）。
