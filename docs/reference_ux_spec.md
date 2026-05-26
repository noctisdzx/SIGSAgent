# Reference UX Spec — `校园人设关系网示意_bilingual.html`

> **Goal.** Give the Vue 3 frontend everything it needs to recreate the look-and-feel of
> the reference HTML page (`校园人设关系网示意_bilingual.html`). All numbers, colors, layout
> rules, vis-network options, and interaction details below are copied verbatim from the
> reference (which lives at the repo root). Where the reference reads from an external
> `sim_data/sim_data.js` (not shipped), the spec describes the expected shape so the
> backend can fulfill the contract.

---

## 1. Global layout

```
┌───────────────────────────────────────────────────────────────────────┐
│  #app  (flex row, height = 100vh)                                     │
│  ┌──────────────────────────┐ ┌──┐ ┌────────────────────────────────┐ │
│  │ #graph-panel (flex:1)    │ │D │ │  #side-panel (default 480 px)  │ │
│  │                          │ │R │ │  width: drag-resizable         │ │
│  │  #mynetwork (vis-network)│ │A │ │  min-width: 320 px             │ │
│  │  #stats  (top-left)      │ │G │ │  bg: #12182b                   │ │
│  │  #search-box (top-right) │ │  │ │  border-left: 1px #1e2a45      │ │
│  │  #btn-lang / btn-reset / │ │HD│ │                                │ │
│  │  btn-toggle (top-right)  │ │L │ │  ┌── .panel-header ──────────┐ │ │
│  │  #legend (bottom-left)   │ │  │ │  │ <h2 id="panel-title"> ... │ │ │
│  │                          │ │6 │ │  └────────────────────────────┘ │ │
│  │                          │ │px│ │  ┌── .tabs #side-tabs ───────┐ │ │
│  │                          │ │  │ │  │ NPC | 关系 | 场景库 | ...  │ │ │
│  │                          │ │  │ │  └────────────────────────────┘ │ │
│  │                          │ │  │ │  ┌── .panel-content ─────────┐ │ │
│  │                          │ │  │ │  │ (renders the active tab)  │ │ │
│  │                          │ │  │ │  └────────────────────────────┘ │ │
│  └──────────────────────────┘ └──┘ └────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

- `body`: `font-family:'Microsoft YaHei','PingFang SC',sans-serif;`
- `body`: `background:#0a0e17; color:#e0e0e0; overflow:hidden`.
- Right-hand `#side-panel` collapses by translating `transform:translateX(100%)` with `transition: transform .3s` when the user clicks `#btn-toggle`.
- A draggable vertical handle `#drag-handle` (6 px wide, color `#1a2240`, hover/dragging color `#42a5f5`) sits between the graph and the side panel. Its width is restored from `localStorage.npcGraphPanelW` and clamped to `[320, window.innerWidth - 200]`. Double-clicking the handle resets to `480 px`. While dragging, `body.resizing` adds `cursor:col-resize; user-select:none` and disables pointer events on `iframe / canvas`.
- The decorative grip inside the handle: a 4×46 pill `#37474f` that turns `#90caf9` on hover.

---

## 2. Color tokens (CSS-ish names; copy verbatim)

| Token                 | Hex      | Used for                                                |
|-----------------------|----------|---------------------------------------------------------|
| `bg-base`             | `#0a0e17`| Page background, scrollbar track                        |
| `bg-panel`            | `#12182b`| Side panel background                                   |
| `bg-card`             | `#0d1220`| Cards (scene, memory, triplet, heat-card, fp-wrap)      |
| `bg-elevated`         | `#1a2240`| Header bar, chips, ctrl-btn bg, fp-tooltip              |
| `bg-elevated-hover`   | `#263259`| Hovered ctrl-btn, active filter-chip, scene-people chip |
| `border-soft`         | `#1e2a45`| All panel/card borders, dotted dividers                 |
| `text-primary`        | `#e0e0e0`| Default body text                                       |
| `text-secondary`      | `#cfd8dc`| Memory text / triplet narrative                         |
| `text-muted`          | `#b0bec5`| Schedule act, node label default                        |
| `text-dim`            | `#90a4ae`| Trigger lines, weather-overcast                         |
| `text-very-dim`       | `#78909c`| `npc-role`, meta numbers, muted hints                   |
| `text-disabled`       | `#546e7a`| Placeholder, schedule labels                            |
| `accent-primary`      | `#90caf9`| Panel headings (`h2`), `npc-name`, links, chips         |
| `accent-active`       | `#42a5f5`| Active tab underline, focused search border, drag-hover |
| `accent-warn`         | `#ffa726`| Section title, schedule time, stats numbers             |
| `accent-warm-soft`    | `#ffe082`| Scene title, hm-bar-label, sched bar-label              |
| `accent-danger`       | `#ef5350`| Lit group dot, tone-tense mem border                    |
| `accent-danger-soft`  | `#ef9a9a`| Taboo chip, negative affinity arrow, contradiction text |
| `accent-good-soft`    | `#a5d6a7`| Comfort chip, positive affinity arrow, tri-obj          |
| `accent-purple-soft`  | `#ce93d8`| Deep-layer text, tone-curious mem border, tri-cn text   |
| `accent-cyan-soft`    | `#80cbc4`| Self-narrative italic                                   |
| `accent-pink`         | `#E91E63`| Edge color for *暧昧/吸引* (attraction)                   |
| `accent-purple`       | `#AB47BC`| Edge color for *师生/职能* (teacher-student)             |
| `accent-yellow-soft`  | `#FFD54F`| Edge color for *崇拜/请教* (admiration)                  |
| `accent-orange-soft`  | `#FF8A65`| Edge color for *合作/项目* (collaboration)               |
| `accent-orange-strong`| `#FF7043`| Edge color for *竞争/张力* (rivalry)                     |
| `accent-green`        | `#66BB6A`| Edge color for *朋友/同好* (friend)                      |
| `accent-blue-soft`    | `#4FC3F7`| Edge color for *学术/同门* (academic)                    |
| `accent-grey`         | `#E0E0E0`| Edge color for *弱连接/偶遇* (weak tie)                  |

Scrollbar (`::-webkit-scrollbar`): 6 px wide, track `#0a0e17`, thumb `#1e2a45` (border-radius 3 px).

---

## 3. Top-of-graph overlays

| Element        | Position                     | Style                                                                 |
|----------------|------------------------------|-----------------------------------------------------------------------|
| `#stats`       | top:16 left:16               | bg `rgba(18,24,43,0.92)`, border `1px #1e2a45`, padding `10px 16px`, font-size 12 px, color `#78909c`; numbers (`<span>`) in `#ffa726` bold. Default text: `节点 60 | 关系 123`. |
| `#search-box`  | top:16 right:460             | rounded pill input, padding `8px 14px`, bg `#12182b`, border `#1e2a45`, focus border `#42a5f5`, width 220 px, placeholder bilingual. |
| `#btn-lang`    | top:16 right:16              | `.ctrl-btn` style, bold; text toggles between `EN` and `中`.            |
| `#btn-reset`   | top:16 right:220             | `.ctrl-btn`, label `重置视图 / Reset View`.                             |
| `#btn-toggle`  | top:16 right:100             | `.ctrl-btn`, label toggles `收起面板 ↔ 展开面板`.                          |
| `#legend`      | bottom:16 left:16            | bg `rgba(18,24,43,0.92)`, border `1px #1e2a45`, max-width 360 px; **两段**：节点分组 + 关系类型；每段下面是 `.legend-row` flex 容器，每个 `.legend-item` 字号 11 px。Node-group items use a circular `.legend-dot` (10×10, border-radius 50%); edge items use a `.legend-line` (18×3, border-radius 2). |

`.ctrl-btn` base: padding `6px 14px`, border-radius `16px`, border `1px #1e2a45`, bg `#1a2240`, color `#90caf9`, font-size 12 px, hover bg `#263259`.

---

## 4. Side-panel header + tabs

- `.panel-header`: padding `16px 20px`, bg `#1a2240`, bottom border `1px #1e2a45`. `<h2>` font-size 16 px, color `#90caf9`. The header text is updated by the active tab's renderer (e.g. `NPC 详情`, `关系履历`, `校园场景库`, `一周高亮事件`, `校园活动热度`).
- `.tabs`: bg `#0d1220`, bottom border `1px #1e2a45`, flex row, `flex-shrink:0`. Each `.tab` is `flex:1`, padding `10px 8px`, text-align center, color `#78909c`, font-size 12 px, `cursor:pointer`, transparent 2-px bottom border. On hover → `#b0bec5`. When `.active`: color `#90caf9`, bottom border `#42a5f5`, bg `#12182b`.
- Tab list (left → right) with `data-tab` attribute + bilingual label:
  1. `data-tab="npc"`     → `NPC` / `NPC`
  2. `data-tab="edge"`    → `关系` / `Edge`
  3. `data-tab="scenes"`  → `场景库` / `Scenes`
  4. `data-tab="timeline"`→ `时间线` / `Timeline`
  5. `data-tab="heatmap"` → `热度` / `Heat`

`.panel-content`: padding `16px 20px`, `overflow-y:auto`, `flex:1`.

---

## 5. vis-network options (exact values)

```js
const options = {
  physics: {
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -40,
      centralGravity:         0.008,
      springLength:           160,
      springConstant:         0.04,
      damping:                0.5,
    },
    stabilization: { iterations: 200 },
  },
  nodes: {
    shape: 'dot',
    size: 16,
    font: { size: 12, color: '#b0bec5', face: 'Microsoft YaHei' },
    borderWidth: 2,
    borderWidthSelected: 3,
    shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 6 },
  },
  edges: {
    width: 1.5,
    font: { size: 9, color: '#546e7a', strokeWidth: 0, face: 'Microsoft YaHei' },
    smooth: { type: 'continuous' },
    arrows: { to: { enabled: false } },        // undirected
    color: { inherit: false, opacity: 0.7 },
    hoverWidth: 3,
  },
  interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true, multiselect: false },
};
```

**Click semantics** (`network.on('click', ...)`):
- Click an empty area → nothing.
- Click a node → switch to `npc` tab, render that NPC, fade non-connected nodes to `opacity:0.15` and connected nodes stay at `opacity:1`. Selected node label uses `size:14 color:#fff`.
- Click an edge → switch to `edge` tab, render edge panel for `from↔to`.
- `network.on('deselectNode')` restores all opacities to 1 and labels to `{size:12,color:'#b0bec5'}`.

**Search** (`#searchInput` input handler): builds a haystack from `name + role + major (+ _en variants)`, sets `opacity:1` for matches and `0.1` for non-matches. Empty input restores all to 1.

**Reset** (`#btn-reset`): `network.fit({animation:true})` + restore all node opacities & default font.

---

## 6. Node-group palette

```js
const groupColorMap = {
  "文学院":     "#EF5350",  // Literature
  "计算机学院": "#42A5F5",  // Computer Science
  "建筑学院":   "#66BB6A",  // Architecture
  "管理学院":   "#FFA726",  // Management
  "理学院":     "#AB47BC",  // Science
  "艺术学院":   "#26C6DA",  // Arts
  "哲学社科":   "#8D6E63",  // Philosophy & Social Sciences
  "外语学院":   "#78909C",  // Foreign Languages
  "教职工":     "#EC407A",  // Faculty
  "后勤":       "#9E9E9E",  // Logistics Staff
  "其他":       "#999",     // Other
};
```

Legend shows counts (e.g. `理学院(13)`).

```js
const GROUP_EN = {
  "文学院":"Literature", "计算机学院":"Computer Science", "建筑学院":"Architecture",
  "管理学院":"Management", "理学院":"Science", "艺术学院":"Arts",
  "哲学社科":"Philosophy & Social Sciences", "外语学院":"Foreign Languages",
  "教职工":"Faculty", "后勤":"Logistics Staff", "其他":"Other", "哲学系":"Philosophy Dept",
};
```

---

## 7. Edge palette (relation kinds)

| Edge color | ZH label       | EN label             | tone     | weight |
|-----------:|----------------|----------------------|----------|-------:|
| `#4FC3F7`  | 学术/同门      | Academic / Cohort    | focused  | 0.78   |
| `#66BB6A`  | 朋友/同好      | Friends / Peers      | warm     | 0.70   |
| `#AB47BC`  | 师生/职能      | Teacher-student      | focused  | 0.82   |
| `#FF8A65`  | 合作/项目      | Collaboration        | decisive | 0.74   |
| `#FF7043`  | 竞争/张力      | Rivalry / Tension    | tense    | 0.65   |
| `#FFD54F`  | 崇拜/请教      | Admiration / Asking  | curious  | 0.60   |
| `#E0E0E0`  | 弱连接/偶遇    | Weak tie / Chance    | casual   | 0.40   |
| `#E91E63`  | 暧昧/吸引      | Attraction / Flirt   | playful  | 0.72   |

(tone/weight columns are how `data/relations.json` materializes the edge for the backend; the HTML only stores color + label.)

---

## 8. Tab 1 — `NPC` panel

Renderer: `renderNPC(id)`. Layout from top to bottom inside `.panel-content`:

1. `<div class="npc-name">` — color `#90caf9`, font-size 22 px, bold.
2. `<div class="npc-role">` — color `#78909c`, font-size 13 px.
3. **Section: `📋 基础身份 / 📋 Basic Identity`**
   - 年龄 / Age (`<n>岁` / `<n> y/o`)
   - 院系 / Major
   - 分组 / Group — rendered as a `.tag` chip with bg = `<groupColor>22` (the `22` is 13% alpha) and text = group color.
4. **Section: `🧬 静态层 · 人格底色 / 🧬 Static · Personality Base`**
   - 先天特质 / Innate trait
   - 后天特质 / Learned trait
   - MBTI — chip bg `#263259`, color `#90caf9`
   - OCEAN — raw string e.g. `O90 C55 E35 A80 N65`
   - 信念 / Belief
   - 长期目标 / Long-term goal
   - 核心矛盾 / Core contradiction — text color `#ef9a9a`
5. **Section: `🎭 双层人格 / 🎭 Dual Persona`**
   - 表层 / Surface
   - 深层 / Deep — text color `#ce93d8`
   - 核心恐惧 / Core fear — text color `#ef9a9a`
   - 核心渴望 / Core desire — text color `#a5d6a7`
6. **Section: `🔄 动态层 · 当前状态 / 🔄 Dynamic · Current State`**
   - 长期欲望 / Long desire
   - 短期目标 / Short goal
   - 当前约束 / Current constraint
   - 感知偏差 / Bias — text color `#ffe082`
   - 自我叙事 / Self narrative — text color `#80cbc4`, italic, wrapped in quotes.
7. **Section: `🏠 生活方式 / 🏠 Lifestyle`** — 作息 / Rhythm / 常见空间.
8. **Section: `📅 今日日程表 / 📅 Today's Schedule`**
   - container `.schedule-wrap` (bg `#0d1220`, border-radius 8, padding 12, margin-top 8)
   - each row `.sch-item` (flex): `.sch-time` (min-width 60, color `#ffa726`, bold) + `.sch-act` (color `#b0bec5`)
9. **Section: `🌍 文化身份 / 🌍 Cultural Identity`** — only if `window.SIM_CULTURE[id]` exists.
   - Fields: nationality / mother tongue / other languages / cultural note.
   - `.chip` (default style) for nationality + mother tongue.
   - `.chip.taboo` for sensitive topics (bg `#3a1a1a`, color `#ef9a9a`, border `#5a2a2a`).
   - `.chip.comfort` for comfort topics (bg `#1a3a2a`, color `#a5d6a7`, border `#2a5a3a`).
   - Hofstede-like dimensions (`individualism / power_distance / uncertainty_avoidance / masculinity / long_term_orientation`) rendered as `.dim-bar` rows:
     - `.dim-label` (120 px, color `#78909c`)
     - `.dim-track` (6 px tall, bg `#0d1220`, border-radius 3)
     - `.dim-fill` (`linear-gradient(90deg,#42a5f5,#ce93d8)`)
     - `.dim-num` (30 px right-aligned, color `#ffa726`, bold)
10. **Section: `🧠 本周记忆（按显著度 Top 25） / 🧠 Weekly Memory (Top 25)`** — only if `SIM_MEMORY[id]` is non-empty.
    - Each `.mem-item` (bg `#0d1220`, padding `8px 10px`, border-radius 4, **left border 3 px**).
    - Left-border color comes from the memory's `tone`:
      - `mem-tone-warm` → `#ffa726`
      - `mem-tone-tense` → `#ef5350`
      - `mem-tone-focused` → `#26c6da`
      - `mem-tone-casual` → `#78909c`
      - `mem-tone-curious` → `#ce93d8`
      - `mem-tone-gentle` → `#a5d6a7`
      - `mem-tone-playful` → `#fff176`
      - `mem-tone-decisive` → `#ff8a65`
      - default → `#42a5f5`
    - `.mem-meta` (font-size 10, color `#78909c`, flex space-between): left = `ts · loc`, right = `显著度 <salience>  亲密 <±affinity>`.
    - `.mem-text` (font-size 12, color `#cfd8dc`, line-height 1.5).
    - `.mem-with` (color `#90caf9`, `text-decoration: underline dotted`) — clickable jump to the partner NPC.
11. **Section: `📡 本周关系雷达 / 📡 Relations This Week`** — top 12 by `|affinity_total|`.
    - Reuses `.mem-item` shell but its left-border color is dynamic:
      - `> +0.05` → `#a5d6a7` plus arrow `↑`
      - `< -0.05` → `#ef9a9a` plus arrow `↓`
      - otherwise → `#90a4ae` plus arrow `→`
12. **Section: `🗺️ 一周足迹 / 🗺️ Weekly Footprint`**
    - `.fp-wrap` (bg `#0d1220`, padding `10px 8px`, border-radius 8, scrollable on x).
    - `.fp-grid-row` per day: `.fp-day-label` (34 px wide, color `#90caf9`, font-size 11) + many `.fp-cell` cells (13×18, margin-right 1, border-radius 2). Hover scales to `1.4` with `outline:1px solid #fff`.
    - Cell color = `activityColor(activityIndex)` where the palette is:
      ```js
      const ACT_PALETTE = ['#455a64','#ffa726','#ce93d8','#42a5f5','#26a69a','#f48fb1','#ef5350',
                           '#ab47bc','#66bb6a','#80cbc4','#a1887f','#fff176','#90a4ae','#7986cb',
                           '#bdbdbd','#5d4037','#37474f'];
      ```
    - `.fp-tick-row` (margin-left 34, every 4th tick shows the hour `HH`, label rotated `-90deg`, font-size 8, color `#546e7a`).
    - Tooltip: a single shared element `#fp-tooltip` (bg `#1a2240`, border `1px #42a5f5`, padding `6px 10px`, font-size 11, color `#cfd8dc`, max-width 260, z-index 200). Shown on `mousemove` by reading `data-fp-tip`.
    - Below the grid: `.fp-stats` (3 stat chips), `.fp-toplocs` (top 6 visited spaces as `.fp-toploc` pills), `.fp-legend` (activity legend sorted by hours).

Default panel (no node clicked) shows the placeholder `点击图谱中的节点查看 NPC 完整画像、文化身份与本周记忆 / Click a node to see NPC profile, cultural identity & memory.` using `.placeholder` (full-height centered, color `#546e7a`, padding 40, text-align center).

---

## 9. Tab 2 — `关系 / Edge` panel

Renderer: `renderEdgePanel(a, b)`. Activated when the user clicks any edge in the graph, OR clicks `.mem-with[data-jump-edge]` in another panel.

1. `<div class="npc-name">` shows `<A>  ⇌  <B>`.
2. `<div class="npc-role">` shows the edge label.
3. `.em-summary` summary card (bg `#0d1220`, padding `10px 12px`, border-radius 6, font-size 12, color `#cfd8dc`):
   - `.em-stat` blocks (margin-right 14, color `#78909c`, font-size 11):
     - `<b>n_interactions</b> 次互动 / interactions`
     - `<b style="color:#a5d6a7|#ef9a9a">+/-affinity</b> 累计亲密 / affinity` (color follows sign)
     - `<b>dominant_tone</b> 主基调 / tone`
   - 2nd row: the textual summary.
4. **Section: `🧩 三元组叙事 / 🧩 Triplet Narrative`**: a list of `.triplet` cards. Each shows
   - `.tri-subj` (color `#90caf9`, bold, clickable jump) - `.tri-pred` (color `#ffa726`, italic) - `.tri-obj` (color `#a5d6a7`, bold, clickable jump) - `.tri-meta` `@<loc>`
   - 2nd line `.tri-meta`: `ts · tone · 亲密 ±delta · 显著 salience`
   - `.tri-narr` (color `#cfd8dc`, font-size 11.5) — full narrative line.
   - Optional `.tri-cn` (color `#ce93d8`, italic, font-size 10.5) — alternate-language line prefixed by `⌬`.

Empty state: `本周这两人没有产生记录在案的互动 / No recorded interaction between them this week.`

---

## 10. Tab 3 — `场景库 / Scenes` panel

Renderer: `renderScenes()`. Reads `window.SIM_SCENES`.

Top of panel:
- A muted hint: `共 N 个基础场景。点击参与者跳到 NPC。 / N base scenes. Click any participant to jump to that NPC.`
- Two filter groups, each rendered as a row of `.filter-chip`s:
  - `按空间 / By space` — auto-derived from `scene.space_zh` (plus an `all` chip).
  - `按天气 / By weather` — auto-derived from `scene.weather` (plus an `all` chip). Each weather-named chip also gets a `.weather-<weather>` class:
    - `.weather-clear` `#ffd54f`, `.weather-rain` `#4fc3f7`, `.weather-overcast` `#90a4ae`,
      `.weather-hot` `#ff7043`, `.weather-cold` `#80deea`, `.weather-snow` `#e1f5fe`.
- Below filters: `当前筛选 / Showing: <b style="color:#ffa726">N</b> 个场景 / scenes`.

`.filter-chip` base: padding `3px 9px`, border-radius 12, bg `#1a2240`, color `#78909c`,
border `1px #263259`, font-size 11. Active state: bg `#263259`, color `#90caf9`, border `#42a5f5`.

Each scene → `.scene-card` (bg `#0d1220`, padding 12, border-radius 8, **left border 3 px `#ffa726`**):
- `.scene-title` (color `#ffe082`, bold, 14 px).
- `.scene-meta` (font-size 11, color `#78909c`): `📍 space · 🕒 time_band · ☁ <weather class>weather · 📅 weekday_pattern`.
- `.scene-trigger` (color `#90a4ae`, italic, 11 px).
- `.scene-people` row of `.chip` pills (bg `#263259`, color `#90caf9`, clickable).
- `.scene-narr` (color `#cfd8dc`, 12 px, line-height 1.6).
- Optional `.scene-toggle` (`▾ 展开三元组叙事 (N)` → `▴` when open), expands a hidden `.triplet` list.
- Optional `可能后果 / Potential outcomes:` muted heading + bullet rows.
- Optional tag chips at the bottom.

---

## 11. Tab 4 — `时间线 / Timeline` panel

Renderer: `renderTimeline()`. Reads `window.SIM_TIMELINE`.

Header: `一周高亮事件 / Weekly Highlights`.
Top hint: `显示模拟一周中显著度 / 亲密变化最大的 N 条事件，按时间排列`.

`.tl-controls` row contains a day filter built from `Array.from(new Set(events.map(e => e.ts.slice(0,10))))` plus an `all` option. Each rendered as `.filter-chip` (same style as Scenes filter chips). Active chip uses the `.filter-chip.active` styling.

Events are then grouped by day. For each new day, a `.tl-day` header (color `#90caf9`, font-size 13, bold, dashed bottom border `#1e2a45`, margin `10px 0 4px`) shows `YYYY-MM-DD (周X / Mon..Sun)`.

Each event row: `.tl-event` (bg `#0d1220`, padding `5px 8px`, border-radius 4, font-size 11.5, **left border `2px #1e2a45`**) containing:
- `.tl-time` (color `#ffa726`, bold, min-width 46 px) — `HH:MM`.
- `.tl-name` (color `#90caf9`, clickable) for subject; on hover color `#fff`.
- `.tri-pred` (color `#ffa726`, italic) for the predicate.
- `.tl-name` for object.
- `.tl-loc` (color `#78909c`, font-size 10) — `@<loc>`.
- Inline affinity delta — color `#a5d6a7` if `>=0` else `#ef9a9a`, font-size 10.
- `.tri-narr` (line below, color `#cfd8dc`).
- Optional `.tl-cn` (color `#ce93d8`, italic, prefix `⌬`).

---

## 12. Tab 5 — `热度 / Heat` panel

Renderer: `renderHeatmap()`. Reads `window.SIM_HEATMAP` (`{ space_zh: { total_npc_ticks, space_zh, space_en, by_tick, by_day_zh, by_day_en, top_npcs[{id, name_zh, name_en, ticks}] } }`) and `window.SIM_FOOTPRINT_META.ticks`.

Header: `校园活动热度 / Campus Activity Heat`.

Behaviour notes copied verbatim:
- The `宿舍 / Dorm Rooms` entry is excluded from the ranking because every NPC sleeps + late-night fallback there, which would crush contrast. A muted hint shows `已隐藏"宿舍"（累计 N 人次时段，因每位 NPC 都会在此过夜，会压扁其它空间的对比度）` (with `border-left:#78909c; color:#90a4ae`).

### Section 1 — `🌡️ 空间热度排行 / 🌡️ Space Heat Ranking`
Each row `.hm-row` (margin-bottom 5, gap 8, flex align center):
- `.hm-space` (108 px, font-size 12, color `#cfd8dc`, text-align right).
- `.hm-bar-wrap` (height 20, bg `#0d1220`, border-radius 4, inset shadow `0 0 0 1px #1a2240`) containing
  `.hm-bar` whose width is `sqrt(total/maxTotal)*100%` and bg is a `linear-gradient(90deg, heatColor(tWidth*0.4), heatColor(tWidth))`. If `tWidth > 0.45`, a `.hm-bar-label` (left 8 top 2, font-size 10.5, color `#fff`, text-shadow `0 1px 2px rgba(0,0,0,0.7)`) renders the raw count.
- `.hm-num` (54 px, color `#ffe082`, font-size 11.5, Consolas monospace) — raw count.

Hint above bars: `一周内每个空间被访问的累计 30 分钟时段（人次 × 半小时格）。条长按 √ 缩放以便弱热点也能看见，色温按相对热度。`.

### Section 2 — `🔥 空间 × 时间 热力网格 / 🔥 Space × Time Heat Grid`
- Hint: `横轴 07:00 → 次日 03:00（每格 30 分钟），纵轴 Top 20 空间。颜色按 √ 缩放，弱热也可见；最热 = 黄。鼠标悬停看精确数。`
- Colorbar row `.hm-colorbar-wrap`: `<冷 / low>` label, `.hm-colorbar` (height 14, border-radius 3, inset border `1px #1a2240`, `background: linear-gradient(90deg, heatColor(0), heatColor(1/6), ..., heatColor(1))`), `<热 / high>` label.
- Tick row `.hm-cb-tick`: 5 values `0, sqrt(0.25)·max, sqrt(0.5)·max, sqrt(0.75)·max, max` (Consolas, 9 px, `#78909c`).
- `.hm-grid-wrap` (bg `#0a0e17`, padding `14px 12px 8px`, border-radius 8, scroll-x, inset shadow `0 0 0 1px #1a2240`).
- `.hm-grid`: vertical stack of `.hm-grid-row`s; first row is the time axis (one `.hm-grid-tick` per 30-min cell, every 4th tick gets `.major` styling = `#cfd8dc` bold, shows the 2-char hour). Other rows: `.hm-grid-label` (96 px, right-aligned, color `#cfd8dc`) + `.hm-grid-cell` (14×18, border-radius 2). Hover scales to 1.4 with `outline:2px solid #fff`. Each cell's title attribute shows `HH:MM · <space> · <n> 人 / npcs`.

### Section 3 — `📊 各空间 Top NPC / 📊 Top NPCs by Space`
Top 18 entries rendered as `.hm-card` (bg `#0d1220`, padding `11px 13px`, border-radius 8, **left border 3 px**; color = `heatColor(sqrt(total/maxTotal))`).
- `.hm-card-title` (color `#ffe082`, font-size 13, bold) — space name with a muted ` · N 人次时段` suffix.
- `.hm-card-meta` (Consolas, color `#78909c`, font-size 11) — `周一:N  周二:N ...`.
- `.hm-top-list` — `.chip` pills (bg `#263259`, color `#90caf9`, clickable jump to that NPC) showing `<name> · <ticks>`.

### Heat color ramp (verbatim)
7-stop sequential ramp interpolated by `t ∈ [0, 1]`:

```
[ 13,  18,  39]  0.00  near-black
[ 40,  11,  84]  0.16  deep purple
[101,  21, 110]  0.33  violet
[165,  44,  96]  0.50  magenta
[222,  73,  65]  0.66  red-orange
[248, 142,  35]  0.83  orange
[252, 230, 110]  1.00  pale yellow
```

`heatColor(0)` returns `#0a0e17`; `heatColor(t>=1)` returns the top stop verbatim; otherwise lerp between adjacent stops.

---

## 13. Bilingual switching

- A single global `currentLang` (`'zh'` or `'en'`).
- All bilingual UI text is declared inline with `data-zh="..." data-en="..."`. Search input uses `data-zh-ph / data-en-ph`. Document title uses `<title data-zh data-en>`.
- `applyLang(lang)` does the following in order:
  1. Set `document.documentElement.lang` to `'en' | 'zh-CN'`.
  2. Iterate every `[data-zh]` element and replace `innerHTML` with `el.dataset[lang]`.
  3. Update `#searchInput.placeholder` to `dataset.<lang>Ph`.
  4. Update `document.title`.
  5. Flip `#btn-lang.textContent` to the *opposite* language tag (`EN` → `中`).
  6. Update every vis node: `{ label: n['label_'+lang], title: n['title_'+lang] }`.
  7. Update every vis edge: `{ label: e['label_'+lang] }`.
  8. Call `rerenderCurrentTab()` so the right side re-paints in the new language.
- Initial language: `applyLang('zh')` at the bottom of the script.

NPC fields are picked via `getField(n, base) = currentLang==='en' ? (n[base+'_en'] || n[base]) : n[base]`. The per-NPC raw schedule string is split on `|` and the leading space-separated token is the time; everything after is the activity narrative.

---

## 14. Click-through / cross-tab navigation

`bindPanelClicks()` is called at the end of every renderer. It wires up:
- `[data-jump-npc]` → `switchTab('npc'); renderNPC(id); network.focus(id, {scale:1.2, animation:true})`.
- `[data-jump-edge]` (value `<aId>-<bId>` produced by `edgeKey(a, b)`) → `switchTab('edge'); renderEdgePanel(a, b)`.
- `[data-toggle]` → toggle visibility of `#<id>` and swap the leading caret between `▾` and `▴`.
- `.scene-filters .filter-chip` (with `data-filter` ∈ `space|weather|day`, `data-val`) → mutates the matching filter then re-renders the active tab.

---

## 15. Persistence

- `localStorage.npcGraphPanelW` — last user-chosen side-panel width.
- No other state is persisted; tab/filters/lang reset on reload.

---

## 16. Backend data contract (what the Vue subagent should expose)

The reference reads from `window.SIM_*` globals. For the Vue port, the equivalent contract is:

| Global              | New REST/WS source                                                | Maps to (data file)                              |
|---------------------|-------------------------------------------------------------------|--------------------------------------------------|
| `NPC_DATA`          | `GET /api/agents` (extended)                                      | `data/personas/*.json` (rich `profile` block)    |
| `nodesRaw`          | derived in front-end from `/api/agents`                           | persona `profile.group_zh` + `groupColorMap`     |
| `edgesRaw`          | `GET /api/relations` (new)                                        | `data/relations.json`                            |
| `SIM_SCENES`        | `GET /api/scenes_library` (new)                                   | `data/scenes_library.json`                       |
| `SIM_TIMELINE`      | initial seed from `GET /api/timeline_seed`, live from `WS /ws`    | `data/timeline_seed.json`                        |
| `SIM_MEMORY[id]`    | `GET /api/agents/{id}/memory` (existing)                          | persistent memory store + `data/memory_seed.json`|
| `SIM_EDGES[edgeKey]`| `GET /api/relations/{aId}-{bId}` (new, aggregated from memories)  | derived live; seeded from `memory_seed`          |
| `SIM_CULTURE[id]`   | `GET /api/agents/{id}` → `profile.culture` (optional)             | persona `profile` (not yet populated)            |
| `SIM_FOOTPRINT[id]` | `GET /api/agents/{id}/footprint` (new, weekly trail)              | derived from schedule + history                  |
| `SIM_FOOTPRINT_META`| `GET /api/footprint/meta`                                         | static: `days_zh/en`, `ticks[]`, pools           |
| `SIM_HEATMAP`       | `GET /api/heatmap` (aggregate)                                    | derived from per-NPC footprints                  |

Where the reference HTML embeds the data in `<script src="sim_data/sim_data.js">` (which is **not shipped**), this repo ships seed JSON in `data/` and lets the live SimLoop populate the rest. The frontend can boot from the seeds and progressively overwrite with `WS /ws` events.

---

## 17. Quick reference — chip / pill / card style index

| Class               | Base bg     | Text       | Border         | Notes                                  |
|---------------------|-------------|------------|----------------|----------------------------------------|
| `.tag`              | (inline)    | (inline)   | none           | Used for group-color, MBTI, etc.       |
| `.chip`             | `#1a2240`   | `#90caf9`  | `1px #263259`  | Cultural chips, scene tags             |
| `.chip.taboo`       | `#3a1a1a`   | `#ef9a9a`  | `1px #5a2a2a`  | Sensitive topic                        |
| `.chip.comfort`     | `#1a3a2a`   | `#a5d6a7`  | `1px #2a5a3a`  | Safe / comfortable topic               |
| `.chip` (scene-people / heat-top) | `#263259` | `#90caf9` | inherit | Clickable jump to NPC          |
| `.filter-chip`      | `#1a2240`   | `#78909c`  | `1px #263259`  | Filter pill                            |
| `.filter-chip.active` | `#263259` | `#90caf9`  | `1px #42a5f5`  | Active filter                          |
| `.scene-card`       | `#0d1220`   | inherit    | left `3px #ffa726` | One social-event vignette          |
| `.mem-item`         | `#0d1220`   | `#cfd8dc`  | left `3px` (tone color) | One memory row                |
| `.triplet`          | `#0d1220`   | inherit    | none           | One subject-predicate-object row       |
| `.hm-card`          | `#0d1220`   | inherit    | left `3px` (heat color) | One heat summary card           |
| `.em-summary`       | `#0d1220`   | `#cfd8dc`  | none           | Edge stat block                        |

End of spec.
