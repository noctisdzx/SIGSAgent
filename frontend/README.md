# SIGSAgent Frontend

Vue 3 + Vite + TypeScript + vis-network + Pinia.

Mirrors the visual contract of `校园人设关系网示意_bilingual.html` and consumes
the live SIGSAgent backend (REST `/api/*` + WebSocket `/ws`).

## Install & run

```powershell
npm install
npm run dev      # → http://127.0.0.1:5173
npm run build    # type-check (vue-tsc --noEmit) + production bundle
npm run preview  # serve the production bundle
```

Vite proxies `/api` and `/ws` to the backend on `127.0.0.1:8000`. If the backend
is offline, every store falls back to a small inline mock (see
`src/mock/data.ts`) so the UI still renders.

## Pages

| Route | File | Purpose |
|---|---|---|
| `/relations` (default) | `views/RelationView.vue` | 60-NPC social graph + 5-tab side panel (NPC / Edge / Scenes / Timeline / Heat). Drag-resizable, bilingual. |
| `/scene` | `views/SceneGraphView.vue` | 16-room topology from `/api/scene/graph`, with per-room metadata + agents-here panel. |
| `/agent`, `/agent/:id` | `views/AgentDetailView.vue` | Searchable NPC list + tabs (Memory / Schedule / Behavior / Perception). |
| `/memory-graph` | `views/MemoryGraphView.vue` | Aggregated triplet (subject → predicate → object) graph across NPCs. |
| `/timeline` | `views/TimelineView.vue` | LEFT: live WS event stream. RIGHT: seeded narrative timeline grouped by day. |

## Reusable components

| Component | Notes |
|---|---|
| `NetworkGraph.vue`        | Generic vis-network wrapper. Exposes `fit()`, `focus(id)`, `setNodeOpacity()`. Emits `selectNode`, `selectEdge`, `deselect`. |
| `NpcDetailPanel.vue`      | Full persona render (basic / static / dual-persona / dynamic / lifestyle / today's schedule). Bilingual via `lang.pickField`. |
| `RelationDetailPanel.vue` | One relation: NPCs, label, weight, tone, color sample. Click NPC chips to jump. |
| `SceneLibraryPanel.vue`   | Filterable list of social-event scenes (by space / weather), expandable cards. |
| `HeatPanel.vue`           | Relation-intensity ranking + NPC×NPC heat matrix using the 7-stop ramp from `docs/reference_ux_spec.md` §12. |
| `MemoryPanel.vue`         | STM/LTM lists with tone-colored left border, hit-count, degraded badge. |
| `SchedulePanel.vue`       | 288 5-min slots compact grid + active slot list. |
| `BehaviorHistory.vue`     | GOAP behavior history rows. |
| `PerceptionPanel.vue`     | Children + siblings perception columns. |
| `TimelineFeed.vue`        | WS event stream renderer (color-coded by type). |
| `Chip.vue`                | Tiny chip with `default / taboo / comfort / filter / people` variants. |

## Pinia stores

| Store | Source | Behavior |
|---|---|---|
| `useLangStore`     | -                          | `'zh' | 'en'` toggle, `t(zh, en)` helper, `pickField(obj, base)`. Persists to `localStorage.npcGraphLang`. |
| `useEventsStore`   | WS                         | Rolling event ring buffer + `connectionStatus`. |
| `useWorldStore`    | `/api/scene/graph`, `/api/world` | Reacts to `tick` events from WS via `applyTick()`. |
| `useAgentsStore`   | `/api/agents/*`            | List + per-id detail/memory/schedule/history cache. |
| `useRelationsStore`| `/api/relations`           | 123 edges. |
| `useScenesStore`   | `/api/scenes-library`      | 37 scenes. |
| `useTimelineStore` | `/api/timeline-seed`       | 35 narrative events. |

Every store sets `usingMock = true` and substitutes inline data from
`src/mock/data.ts` if the corresponding endpoint errors out.

## WebSocket

`src/api/ws.ts` opens `ws://${location.host}/ws` with exponential backoff
(`1s → 15s` cap) and updates `useEventsStore().connectionStatus`. Handles
`welcome`, `tick`, `agent_decision`, `behavior`, `agent_error`, etc.

## Theme tokens

All colors live in CSS custom properties on `:root` in `src/styles.css`,
mirroring §2 of `docs/reference_ux_spec.md`. Group / edge palettes are baked
into `RelationView.vue` per spec §6 / §7.
