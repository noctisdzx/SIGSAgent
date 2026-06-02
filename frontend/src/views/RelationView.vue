<!--
  Relation view (campus social graph) — main page.

  Mirrors `校园人设关系网示意_bilingual.html` and §1-§14 of `docs/reference_ux_spec.md`.
  Layout:
    +---- left graph panel ----+ DRAG +---- right side panel ----+
    | vis-network              |  ┃   | header (panel-title)     |
    | overlays:                |  ┃   | tabs: NPC | Edge | Scenes|
    |  - stats (top-left)      |  ┃   |        | Timeline | Heat |
    |  - search (top-right)    |  ┃   | content (active tab)     |
    |  - reset/collapse btns   |  ┃   |                          |
    |  - legend (bottom-left)  |  ┃   |                          |
    +--------------------------+      +--------------------------+

  Side-panel width is drag-resizable (min 320, default 480) and persisted
  to `localStorage.npcGraphPanelW`. Double-click the handle resets to 480.
-->
<template>
  <div class="rv" :class="{ collapsed }">
    <!-- LEFT: graph -->
    <div class="rv-graph">
      <NetworkGraph
        ref="graphRef"
        :nodes="vNodes"
        :edges="vEdges"
        @select-node="onSelectNode"
        @select-edge="onSelectEdge"
        @deselect="onDeselect"
      />

      <!-- top-left stats -->
      <div class="stats">
        <span>{{ lang.t('节点', 'Nodes') }}
          <b>{{ npcs.length }}</b></span>
        <span>{{ lang.t('关系', 'Edges') }}
          <b>{{ edges.length }}</b></span>
        <span class="mock-flag" v-if="usingMock">
          {{ lang.t('· 离线 mock', '· offline mock') }}
        </span>
      </div>

      <!-- top-right controls -->
      <div class="topright">
        <input
          v-model="searchTerm"
          class="search-box"
          :placeholder="lang.t('搜索 NPC 姓名或角色…', 'Search NPC name or role…')"
          @input="onSearch"
        />
        <button class="ctrl-btn" @click="resetView">
          {{ lang.t('重置视图', 'Reset View') }}
        </button>
        <button class="ctrl-btn" @click="collapsed = !collapsed">
          {{ collapsed ? lang.t('展开面板', 'Expand') : lang.t('收起面板', 'Collapse') }}
        </button>
      </div>

      <!-- bottom-left legend -->
      <div class="legend">
        <div class="legend-title">{{ lang.t('节点分组', 'Node Groups') }}</div>
        <div class="legend-row">
          <span v-for="(c, k) in groupColorMap" :key="k" class="legend-item">
            <span class="legend-dot" :style="{ background: c }"></span>
            {{ groupLabel(k) }}<span class="cnt" v-if="groupCounts[k]">({{ groupCounts[k] }})</span>
          </span>
        </div>
        <div class="legend-title">{{ lang.t('关系类型', 'Edge Types') }}</div>
        <div class="legend-row">
          <span v-for="ek in edgeKindList" :key="ek.color" class="legend-item">
            <span class="legend-line" :style="{ background: ek.color }"></span>
            {{ lang.lang === 'en' ? ek.en : ek.zh }}
          </span>
        </div>
      </div>
    </div>

    <!-- DRAG handle -->
    <div
      class="drag-handle"
      :class="{ active: dragging }"
      @mousedown="startDrag"
      @dblclick="resetWidth"
    >
      <span class="grip" />
    </div>

    <!-- RIGHT: side panel -->
    <aside class="rv-side" :style="{ width: collapsed ? '0px' : panelW + 'px' }">
      <div class="panel-header">
        <h2>{{ headerTitle }}</h2>
      </div>
      <div class="tabs">
        <span
          v-for="t in tabs"
          :key="t.key"
          class="tab"
          :class="{ active: activeTab === t.key }"
          @click="activeTab = t.key"
        >
          {{ lang.lang === 'en' ? t.en : t.zh }}
        </span>
      </div>
      <div class="panel-content">
        <NpcDetailPanel
          v-if="activeTab === 'npc'"
          :npc="selectedNpcDetail"
          :group-color-map="groupColorMap"
        />
        <RelationDetailPanel
          v-else-if="activeTab === 'edge'"
          :edge="selectedEdge"
          :npc-map="npcMap"
          @jump-npc="jumpToNpc"
        />
        <SceneLibraryPanel
          v-else-if="activeTab === 'scenes'"
          :scenes="scenes.scenes"
          :npc-map="npcMap"
          :room-name-map="roomNameMap"
          @jump-npc="jumpToNpc"
        />
        <div v-else-if="activeTab === 'timeline'" class="timeline-tab">

          <!-- ============== Per-NPC runtime timeline ============== -->
          <section class="npc-tl">
            <h3 class="block-title">
              📋 {{ lang.t('当前 NPC：', 'Current NPC: ') }}
              <span v-if="selectedNpcDetail?.name" class="cur-npc">
                {{ lang.lang === 'en'
                    ? (selectedNpcDetail.name_en || selectedNpcDetail.name)
                    : selectedNpcDetail.name }}
              </span>
              <span v-else class="cur-npc dim">
                {{ lang.t('（点击图中节点选择）', '(click a node in the graph)') }}
              </span>
            </h3>
            <div v-if="!selectedNpcDetail" class="placeholder-block">
              {{ lang.t('选中一个 NPC 即可看到其正在采用的日程与已执行行为。',
                       'Select an NPC to see its current schedule and executed actions.') }}
            </div>
            <template v-else>
              <div class="sim-now">
                ⏱ {{ lang.t('当前 sim 时间', 'Sim time') }}:
                <b>{{ simHHMM || '—' }}</b>
                <span class="dim">· {{ lang.t('日期', 'day') }} {{ sim.currentDay || '—' }}</span>
              </div>

              <div class="sched-group">
                <div class="sg-label sg-now">
                  🟢 {{ lang.t('正在进行', 'Now') }}
                </div>
                <div v-if="!npcNowSlot" class="placeholder-block small">
                  {{ lang.t('当前没有锚定的日程。', 'No anchored slot right now.') }}
                </div>
                <div v-else class="slot-row now">
                  <span class="tl-time">{{ shortIso(npcNowSlot.start) }}–{{ shortIso(npcNowSlot.end) }}</span>
                  <span class="tl-name">{{ npcNowSlot.activity || '(idle)' }}</span>
                  <span v-if="npcNowSlot.location_uid" class="tl-loc">
                    @{{ roomNameMap[npcNowSlot.location_uid] || npcNowSlot.location_uid }}
                  </span>
                  <span class="slot-kind">[{{ npcNowSlot.kind }}]</span>
                </div>
              </div>

              <div class="sched-group">
                <div class="sg-label sg-hist">
                  ✓ {{ lang.t('已执行行为', 'Executed') }}
                  <span class="dim">({{ npcRecentHistory.length }} {{ lang.t('条', '') }})</span>
                </div>
                <div v-if="!npcRecentHistory.length" class="placeholder-block small">
                  {{ lang.t('该 NPC 尚未执行任何动作。', 'This NPC has not acted yet.') }}
                </div>
                <div v-for="(h, i) in npcRecentHistory" :key="`h${i}`"
                     class="slot-row" :class="{ failed: h.ok === false }">
                  <span class="tl-time">{{ shortIso(h.ts) }}</span>
                  <span class="tl-name">
                    {{ h.ok === false ? '✗' : '✓' }} {{ h.action_id }}
                  </span>
                  <span v-if="h.params && Object.keys(h.params).length" class="slot-params">
                    {{ JSON.stringify(h.params) }}
                  </span>
                  <span v-if="h.note" class="tri-narr">— {{ h.note }}</span>
                </div>
              </div>

              <div class="sched-group">
                <div class="sg-label sg-next">
                  ⏭ {{ lang.t('即将进行', 'Upcoming') }}
                </div>
                <div v-if="!npcUpcomingSlots.length" class="placeholder-block small">
                  {{ lang.t('今天后续无更多锚定日程。', 'No further anchored slots today.') }}
                </div>
                <div v-for="(s, i) in npcUpcomingSlots" :key="`u${i}`" class="slot-row">
                  <span class="tl-time">{{ shortIso(s.start) }}</span>
                  <span class="tl-name">{{ s.activity }}</span>
                  <span v-if="s.location_uid" class="tl-loc">
                    @{{ roomNameMap[s.location_uid] || s.location_uid }}
                  </span>
                  <span class="slot-kind">[{{ s.kind }}]</span>
                </div>
              </div>
            </template>
          </section>

          <!-- ============== Seeded weekly highlights ============== -->
          <section class="seed-tl">
            <h3 class="block-title block-title--folded"
                :class="{ open: showSeedTimeline }"
                @click="showSeedTimeline = !showSeedTimeline">
              <span class="caret">{{ showSeedTimeline ? '▾' : '▸' }}</span>
              📅 {{ lang.t('一周高亮（剧本预设）', 'Weekly Highlights (scripted)') }}
              <span class="block-meta">{{ lang.t(`(${timeline.seedEvents.length} 条)`,
                                         `(${timeline.seedEvents.length})`) }}</span>
            </h3>
            <div v-show="showSeedTimeline">
              <div class="filter-row">
                <span class="row-label">{{ lang.t('按日期', 'By day') }}</span>
                <span class="filter-chip" :class="{ active: dayFilter === 'all' }"
                      @click="dayFilter = 'all'">{{ lang.t('全部', 'All') }}</span>
                <span v-for="d in availableDays" :key="d"
                      class="filter-chip" :class="{ active: dayFilter === d }"
                      @click="dayFilter = d">{{ d }}</span>
              </div>
              <template v-for="d in groupedDays" :key="d.day">
                <div class="tl-day">{{ d.day }}</div>
                <div v-for="(ev, i) in d.events" :key="i" class="tl-event">
                  <span class="tl-time">{{ ev.time || (ev.ts || '').slice(11, 16) }}</span>
                  <span class="tl-name">{{ titleOf(ev) }}</span>
                  <span v-if="ev.location_uid" class="tl-loc">@{{ ev.location_uid }}</span>
                  <div class="tri-narr">{{ narrativeOf(ev) }}</div>
                </div>
              </template>
              <div v-if="!filteredTimeline.length" class="placeholder-block">
                {{ lang.t('无时间线事件。', 'No timeline events.') }}
              </div>
            </div>
          </section>
        </div>
        <HeatPanel
          v-else-if="activeTab === 'heatmap'"
          :edges="edges"
          :npc-map="npcMap"
        />
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
import NpcDetailPanel from '@/components/NpcDetailPanel.vue';
import RelationDetailPanel from '@/components/RelationDetailPanel.vue';
import SceneLibraryPanel from '@/components/SceneLibraryPanel.vue';
import HeatPanel from '@/components/HeatPanel.vue';
import { useLangStore } from '@/stores/lang';
import { useAgentsStore } from '@/stores/agents';
import { useRelationsStore, edgeFromTo } from '@/stores/relations';
import { useScenesStore } from '@/stores/scenes';
import { useTimelineStore } from '@/stores/timeline';
import { useWorldStore } from '@/stores/world';
import { useSimStore } from '@/stores/sim';
import type { RelationEdge, AgentLite, TimelineEvent } from '@/api/endpoints';

const lang = useLangStore();
const agentsStore = useAgentsStore();
const relationsStore = useRelationsStore();
const scenes = useScenesStore();
const timeline = useTimelineStore();
const world = useWorldStore();
const sim = useSimStore();

/* ----------------------------------------------------------------- *
 * Group palette (verbatim from spec §6).                              *
 * ----------------------------------------------------------------- */
const groupColorMap: Record<string, string> = {
  '文学院':     '#EF5350',
  '计算机学院': '#42A5F5',
  '建筑学院':   '#66BB6A',
  '管理学院':   '#FFA726',
  '理学院':     '#AB47BC',
  '艺术学院':   '#26C6DA',
  '哲学社科':   '#8D6E63',
  '外语学院':   '#78909C',
  '教职工':     '#EC407A',
  '后勤':       '#9E9E9E',
  '其他':       '#999',
};
const GROUP_EN: Record<string, string> = {
  '文学院': 'Literature', '计算机学院': 'Computer Science', '建筑学院': 'Architecture',
  '管理学院': 'Management', '理学院': 'Science', '艺术学院': 'Arts',
  '哲学社科': 'Philosophy & Social Sciences', '外语学院': 'Foreign Languages',
  '教职工': 'Faculty', '后勤': 'Logistics Staff', '其他': 'Other',
};
function groupLabel(k: string): string {
  return lang.lang === 'en' ? (GROUP_EN[k] || k) : k;
}

const edgeKindList = [
  { color: '#4FC3F7', zh: '学术/同门',   en: 'Academic / Cohort' },
  { color: '#66BB6A', zh: '朋友/同好',   en: 'Friends / Peers' },
  { color: '#AB47BC', zh: '师生/职能',   en: 'Teacher-student' },
  { color: '#FF8A65', zh: '合作/项目',   en: 'Collaboration' },
  { color: '#FF7043', zh: '竞争/张力',   en: 'Rivalry / Tension' },
  { color: '#FFD54F', zh: '崇拜/请教',   en: 'Admiration / Asking' },
  { color: '#E0E0E0', zh: '弱连接/偶遇', en: 'Weak tie / Chance' },
  { color: '#E91E63', zh: '暧昧/吸引',   en: 'Attraction / Flirt' },
];

/* ----------------------------------------------------------------- *
 * Data                                                                *
 * ----------------------------------------------------------------- */
const npcs = computed<AgentLite[]>(() => agentsStore.list);
const edges = computed<RelationEdge[]>(() => relationsStore.edges);
const usingMock = computed(() =>
  agentsStore.usingMock || relationsStore.usingMock || scenes.usingMock || timeline.usingMock,
);

const npcMap = computed<Record<string, AgentLite>>(() => {
  const m: Record<string, AgentLite> = {};
  for (const a of npcs.value) m[String(a.id)] = a;
  return m;
});

const roomNameMap = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {};
  for (const r of (world.sceneGraph?.rooms || [])) m[r.uid] = r.name;
  return m;
});

const groupCounts = computed<Record<string, number>>(() => {
  const c: Record<string, number> = {};
  for (const a of npcs.value) {
    const g = (a as any).group || (a as any).group_zh || '其他';
    c[g] = (c[g] || 0) + 1;
  }
  return c;
});

/* ----------------------------------------------------------------- *
 * vis-network nodes/edges                                             *
 * ----------------------------------------------------------------- */
const vNodes = computed<any[]>(() => {
  return npcs.value.map(a => {
    const groupKey = (a as any).group || (a as any).group_zh || '其他';
    const color = (a as any).color || groupColorMap[groupKey] || '#999';
    const labelZh = (a as any).name || String(a.id);
    const labelEn = (a as any).name_en || labelZh;
    const titleZh = `${labelZh} | ${a.role || ''}`;
    const titleEn = `${labelEn} | ${(a as any).role_en || a.role || ''}`;
    return {
      id: a.id,
      label: lang.lang === 'en' ? labelEn : labelZh,
      title: lang.lang === 'en' ? titleEn : titleZh,
      group: groupKey,
      color: { background: color, border: color, highlight: { background: color, border: '#fff' } },
    };
  });
});

const vEdges = computed<any[]>(() => {
  return edges.value.map((e, i) => {
    const ft = edgeFromTo(e);
    const lbl = lang.lang === 'en'
      ? (e.label_en || e.label || '')
      : (e.label || e.label_en || '');
    return {
      id: (e as any).id ?? i,
      from: ft.from,
      to: ft.to,
      label: lbl,
      title: lbl,
      color: { color: e.color || '#42a5f5', opacity: 0.7 },
      width: 1.5 + Math.max(0, Math.min(1.5, (e.weight ?? 0) * 1.4)),
    };
  });
});

/* ----------------------------------------------------------------- *
 * Tabs / selection                                                    *
 * ----------------------------------------------------------------- */
type TabKey = 'npc' | 'edge' | 'scenes' | 'timeline' | 'heatmap';
const tabs: Array<{ key: TabKey; zh: string; en: string }> = [
  { key: 'npc',      zh: 'NPC',    en: 'NPC' },
  { key: 'edge',     zh: '关系',    en: 'Edge' },
  { key: 'scenes',   zh: '场景库',  en: 'Scenes' },
  { key: 'timeline', zh: '时间线',  en: 'Timeline' },
  { key: 'heatmap',  zh: '热度',    en: 'Heat' },
];
const activeTab = ref<TabKey>('npc');

const selectedNpcId = ref<string | null>(null);
const selectedNpcDetail = ref<any | null>(null);
const selectedEdge = ref<RelationEdge | null>(null);

const headerTitle = computed(() => {
  switch (activeTab.value) {
    case 'edge':     return lang.t('关系履历', 'Relation History');
    case 'scenes':   return lang.t('校园场景库', 'Campus Scenes');
    case 'timeline': return lang.t('一周高亮事件', 'Weekly Highlights');
    case 'heatmap':  return lang.t('校园活动热度', 'Campus Heat');
    case 'npc':
    default:         return lang.t('NPC 详情', 'NPC Details');
  }
});

const graphRef = ref<InstanceType<typeof NetworkGraph> | null>(null);

async function onSelectNode(id: string) {
  selectedNpcId.value = id;
  activeTab.value = 'npc';
  // Full select() also primes schedule + history so the Timeline tab can
  // render this NPC's current/past/upcoming activities immediately.
  await agentsStore.select(id);
  selectedNpcDetail.value = agentsStore.detail;
  // Dim non-connected nodes.
  const connected = new Set<string | number>([id]);
  for (const e of edges.value) {
    const ft = edgeFromTo(e);
    if (String(ft.from) === String(id)) connected.add(ft.to);
    if (String(ft.to) === String(id))   connected.add(ft.from);
  }
  graphRef.value?.setNodeOpacity?.(connected, 0.15);
}
function onSelectEdge(_eid: string | number, ft: { from: string; to: string }) {
  const found = edges.value.find(e => {
    const f = edgeFromTo(e);
    return (String(f.from) === ft.from && String(f.to) === ft.to)
        || (String(f.from) === ft.to   && String(f.to) === ft.from);
  });
  selectedEdge.value = found || null;
  activeTab.value = 'edge';
}
function onDeselect() {
  graphRef.value?.resetNodeOpacity?.();
}

async function jumpToNpc(id: string) {
  selectedNpcId.value = id;
  activeTab.value = 'npc';
  await agentsStore.select(id);
  selectedNpcDetail.value = agentsStore.detail;
  graphRef.value?.focus?.(id);
}

/* ----------------------------------------------------------------- *
 * Search                                                              *
 * ----------------------------------------------------------------- */
const searchTerm = ref('');
function onSearch() {
  const q = searchTerm.value.trim().toLowerCase();
  if (!q) { graphRef.value?.resetNodeOpacity?.(); return; }
  const matched = new Set<string | number>();
  for (const a of npcs.value) {
    const hay = [
      (a as any).name, (a as any).name_en,
      a.role, (a as any).role_en,
      (a as any).major, (a as any).major_en,
      (a as any).group, (a as any).group_en,
    ].filter(Boolean).join(' ').toLowerCase();
    if (hay.includes(q)) matched.add(a.id);
  }
  graphRef.value?.setNodeOpacity?.(matched, 0.1);
}
function resetView() {
  graphRef.value?.fit?.();
  graphRef.value?.resetNodeOpacity?.();
  searchTerm.value = '';
}

/* ----------------------------------------------------------------- *
 * Drag-resize side panel                                              *
 * ----------------------------------------------------------------- */
const DEFAULT_W = 480;
const MIN_W = 320;
function clampW(w: number): number {
  const max = (typeof window !== 'undefined' ? window.innerWidth : 1600) - 200;
  return Math.max(MIN_W, Math.min(max, w));
}
const panelW = ref<number>(DEFAULT_W);
const collapsed = ref(false);
const dragging = ref(false);

onMounted(() => {
  try {
    const saved = Number(localStorage.getItem('npcGraphPanelW') || '');
    if (Number.isFinite(saved) && saved >= MIN_W) panelW.value = clampW(saved);
  } catch { /* ignore */ }
});

let dragStartX = 0;
let dragStartW = 0;
function startDrag(ev: MouseEvent) {
  if (collapsed.value) return;
  dragging.value = true;
  dragStartX = ev.clientX;
  dragStartW = panelW.value;
  document.body.classList.add('resizing');
  window.addEventListener('mousemove', onDrag);
  window.addEventListener('mouseup', endDrag);
}
function onDrag(ev: MouseEvent) {
  if (!dragging.value) return;
  const dx = dragStartX - ev.clientX;
  panelW.value = clampW(dragStartW + dx);
}
function endDrag() {
  if (!dragging.value) return;
  dragging.value = false;
  document.body.classList.remove('resizing');
  window.removeEventListener('mousemove', onDrag);
  window.removeEventListener('mouseup', endDrag);
  try { localStorage.setItem('npcGraphPanelW', String(panelW.value)); } catch { /* ignore */ }
}
function resetWidth() {
  panelW.value = DEFAULT_W;
  try { localStorage.setItem('npcGraphPanelW', String(DEFAULT_W)); } catch { /* ignore */ }
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDrag);
  window.removeEventListener('mouseup', endDrag);
  document.body.classList.remove('resizing');
});

/* ----------------------------------------------------------------- *
 * Timeline tab                                                        *
 * ----------------------------------------------------------------- */
const dayFilter = ref<string>('all');
const availableDays = computed<string[]>(() => {
  const set = new Set<string>();
  for (const ev of timeline.seedEvents) {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '');
    if (d) set.add(d);
  }
  return Array.from(set).sort();
});
const filteredTimeline = computed<TimelineEvent[]>(() => {
  if (dayFilter.value === 'all') return timeline.seedEvents;
  return timeline.seedEvents.filter(ev => {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '');
    return d === dayFilter.value;
  });
});
const groupedDays = computed(() => {
  const map: Record<string, TimelineEvent[]> = {};
  for (const ev of filteredTimeline.value) {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '—');
    (map[d] = map[d] || []).push(ev);
  }
  return Object.entries(map).map(([day, events]) => ({ day, events }));
});
function titleOf(ev: TimelineEvent): string {
  return lang.lang === 'en' ? (ev.title_en || ev.title || '') : (ev.title || ev.title_en || '');
}
function narrativeOf(ev: TimelineEvent): string {
  return lang.lang === 'en' ? (ev.narrative_en || ev.narrative_zh || '') : (ev.narrative_zh || ev.narrative_en || '');
}
function shortIso(iso?: string): string {
  if (!iso) return '';
  try { return iso.slice(11, 16); } catch { return iso; }
}

/* ----------------------------------------------------------------- *
 * Per-NPC runtime timeline                                            *
 * ----------------------------------------------------------------- */
const showSeedTimeline = ref(false);

const simHHMM = computed(() => shortIso(sim.simTime));

const npcSchedule = computed<any>(() => agentsStore.schedule);
const npcHistory = computed<any[]>(() => agentsStore.history || []);

/** All non-empty slots in order. */
const npcSlots = computed<any[]>(() => (npcSchedule.value?.slots || []));

/** The slot that wraps `simTime` (start <= simTime < end). */
const npcNowSlot = computed<any | null>(() => {
  const t = sim.simTime;
  if (!t || !npcSlots.value.length) return null;
  for (const s of npcSlots.value) {
    if (s.start <= t && t < s.end) return s;
  }
  return null;
});

/** Up-to-next 6 slots after the current sim time. */
const npcUpcomingSlots = computed<any[]>(() => {
  const t = sim.simTime;
  if (!t) return [];
  return npcSlots.value.filter(s => s.start > t).slice(0, 6);
});

/** Most recent 12 actions, newest first. */
const npcRecentHistory = computed<any[]>(() => {
  const arr = [...npcHistory.value];
  arr.sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')));
  return arr.slice(0, 12);
});

/* ----------------------------------------------------------------- *
 * Bootstrap                                                           *
 * ----------------------------------------------------------------- */
onMounted(async () => {
  await Promise.all([
    agentsStore.loadList(),
    relationsStore.load(),
    scenes.load(),
    timeline.loadSeed(),
    world.loadScene(),
    world.loadWorld(),
  ]);
});

// Keep search consistent if language flips while a query is active.
watch(() => lang.lang, () => onSearch());
</script>

<style scoped>
.rv {
  display: flex;
  height: 100%;
  background: var(--bg-base);
}
.rv-graph {
  flex: 1;
  position: relative;
  min-width: 0;
}

/* top-left stats */
.stats {
  position: absolute;
  top: 16px; left: 16px;
  background: rgba(18,24,43,0.92);
  border: 1px solid var(--border-soft);
  padding: 8px 14px;
  font-size: 12px;
  color: var(--text-very-dim);
  border-radius: 12px;
  display: flex; gap: 14px;
  z-index: 5;
}
.stats b { color: var(--accent-warn); margin-left: 4px; }
.mock-flag { color: var(--accent-warn); }

/* top-right controls */
.topright {
  position: absolute;
  top: 16px; right: 16px;
  display: flex; gap: 8px; align-items: center;
  z-index: 5;
}
.search-box {
  width: 220px;
  padding: 8px 14px;
  border-radius: 16px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  border: 1px solid var(--border-soft);
  outline: none;
  font-size: 12px;
}
.search-box:focus { border-color: var(--accent-active); }

/* bottom-left legend */
.legend {
  position: absolute;
  bottom: 16px; left: 16px;
  max-width: 380px;
  background: rgba(18,24,43,0.92);
  border: 1px solid var(--border-soft);
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  z-index: 5;
}
.legend-title {
  color: var(--accent-warm-soft);
  font-weight: 600;
  margin-top: 4px;
  margin-bottom: 4px;
}
.legend-row {
  display: flex; flex-wrap: wrap; gap: 8px 14px;
  margin-bottom: 4px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-very-dim);
}
.legend-item .cnt { color: var(--text-disabled); margin-left: 2px; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; }
.legend-line { width: 18px; height: 3px; border-radius: 2px; }

/* drag handle */
.drag-handle {
  width: 6px;
  cursor: col-resize;
  background: var(--bg-elevated);
  position: relative;
  z-index: 6;
  transition: background .2s;
}
.drag-handle:hover, .drag-handle.active { background: var(--accent-active); }
.grip {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 4px; height: 46px;
  background: #37474f;
  border-radius: 3px;
  transition: background .2s;
}
.drag-handle:hover .grip, .drag-handle.active .grip { background: var(--accent-primary); }

.rv.collapsed .drag-handle { display: none; }
.rv.collapsed .rv-side { width: 0 !important; }

/* right side panel */
.rv-side {
  background: var(--bg-panel);
  border-left: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width .25s ease;
  overflow: hidden;
}
.panel-header {
  padding: 14px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.panel-header h2 {
  font-size: 16px;
  color: var(--accent-primary);
  font-weight: 600;
}
.tabs {
  display: flex;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.tab {
  flex: 1;
  text-align: center;
  padding: 10px 8px;
  font-size: 12px;
  color: var(--text-very-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.tab:hover { color: var(--text-muted); }
.tab.active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-active);
  background: var(--bg-panel);
}
.panel-content {
  padding: 14px 18px;
  flex: 1;
  overflow-y: auto;
  font-size: 12.5px;
}

/* timeline tab styles */
.timeline-tab .tl-day {
  color: var(--accent-primary);
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px dashed var(--border-soft);
  margin: 12px 0 4px;
  padding-bottom: 2px;
}
.tl-event {
  background: var(--bg-card);
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid var(--border-soft);
  margin-bottom: 4px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.tl-event .tl-time {
  color: var(--accent-warn);
  font-weight: 600;
  min-width: 46px;
  display: inline-block;
  font-family: Consolas, monospace;
  margin-right: 6px;
}
.tl-event .tl-name { color: var(--accent-primary); }
.tl-event .tl-loc  { color: var(--text-very-dim); font-size: 10px; margin-left: 6px; }
.tl-event .tri-narr {
  color: var(--text-secondary);
  font-size: 11px;
  margin-top: 2px;
  line-height: 1.5;
}
.placeholder-block {
  color: var(--text-disabled);
  font-size: 12px;
  text-align: center;
  padding: 20px 0;
}

.filter-row {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 8px;
}
.row-label { font-size: 11px; color: var(--text-very-dim); margin-right: 8px; }

/* per-NPC timeline */
.npc-tl { margin-bottom: 16px; }
.block-title {
  color: var(--accent-warn);
  font-size: 13.5px;
  font-weight: 600;
  margin: 6px 0 8px;
}
.block-title--folded {
  cursor: pointer; user-select: none;
  color: var(--text-muted);
  background: rgba(255,255,255,0.02);
  padding: 6px 8px;
  border-radius: 6px;
  display: flex; align-items: center; gap: 6px;
  border-top: 1px dashed var(--border-soft);
  margin-top: 16px;
}
.block-title--folded.open { color: var(--accent-warn); }
.block-title--folded:hover { background: rgba(255,255,255,0.05); }
.block-title--folded .caret { font-size: 11px; color: var(--text-very-dim); }
.block-title--folded .block-meta {
  margin-left: auto;
  color: var(--text-very-dim);
  font-size: 10.5px;
  font-weight: 400;
}
.cur-npc {
  color: var(--accent-primary);
  font-weight: 700;
}
.cur-npc.dim { color: var(--text-very-dim); font-weight: 400; }
.sim-now {
  font-size: 11.5px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.sim-now b { color: var(--accent-warn); margin: 0 4px; font-family: Consolas, monospace; }
.sim-now .dim { color: var(--text-very-dim); margin-left: 8px; }
.sched-group { margin-bottom: 12px; }
.sg-label {
  font-size: 11.5px;
  color: var(--text-very-dim);
  margin-bottom: 4px;
  font-weight: 600;
}
.sg-now { color: #66BB6A; }
.sg-hist { color: var(--accent-primary); }
.sg-next { color: var(--accent-warm-soft); }
.sg-label .dim { color: var(--text-very-dim); font-weight: 400; margin-left: 4px; }

.slot-row {
  background: var(--bg-card);
  padding: 5px 10px;
  border-radius: 4px;
  border-left: 2px solid var(--border-soft);
  margin-bottom: 4px;
  font-size: 11.5px;
  color: var(--text-secondary);
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px;
}
.slot-row.now {
  border-left-color: #66BB6A;
  background: rgba(102, 187, 106, 0.08);
}
.slot-row.failed {
  border-left-color: var(--accent-danger, #EF5350);
  color: var(--text-very-dim);
}
.slot-row .tl-time {
  color: var(--accent-warn); font-weight: 600;
  font-family: Consolas, monospace; min-width: 90px;
}
.slot-row .tl-name { color: var(--accent-primary); font-weight: 500; }
.slot-row .tl-loc { color: var(--text-very-dim); font-size: 10.5px; }
.slot-row .slot-kind {
  color: var(--text-very-dim); font-size: 10px; margin-left: auto;
  font-family: Consolas, monospace;
}
.slot-row .slot-params {
  color: var(--text-very-dim); font-size: 10.5px;
  font-family: Consolas, monospace;
}
.slot-row .tri-narr {
  color: var(--text-very-dim);
  font-size: 11px;
  margin-top: 2px;
  flex-basis: 100%;
}
.placeholder-block.small { font-size: 11.5px; padding: 6px 0; }
</style>
