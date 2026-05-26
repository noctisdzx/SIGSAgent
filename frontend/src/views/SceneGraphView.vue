<!--
  Scene topology view.
  Renders the 16-room adjacency graph from `/api/scene/graph`.
  Click a room → side panel shows room metadata + agents currently inside.
-->
<template>
  <div class="scene-page">
    <div class="scene-graph">
      <NetworkGraph
        ref="graphRef"
        :nodes="vNodesAll"
        :edges="vEdgesAll"
        :options="opts"
        @select-node="onSelectNode"
      />
      <div class="stats">
        <span>{{ lang.t('房间', 'Rooms') }}
          <b>{{ rooms.length }}</b></span>
        <span>{{ lang.t('相邻边', 'Adjacencies') }}
          <b>{{ vEdges.length }}</b></span>
        <span>{{ lang.t('追踪中', 'Tracking') }}
          <b>{{ trackedAgents.length }}</b></span>
        <span v-if="world.lastTickAt" class="sim-clock">
          ⏱ {{ shortTime(world.lastTickAt) }}
        </span>
      </div>

      <div class="tracker-panel">
        <div class="tracker-header">
          <strong>{{ lang.t('NPC 实时追踪', 'Track NPC moves') }}</strong>
          <div class="tracker-actions">
            <button @click="trackAll" class="micro-btn">{{ lang.t('全部', 'All') }}</button>
            <button @click="trackNone" class="micro-btn">{{ lang.t('清空', 'None') }}</button>
          </div>
        </div>
        <input
          v-model="filterText"
          :placeholder="lang.t('按姓名/id 过滤…', 'filter by name/id…')"
          class="tracker-filter"
        />
        <div class="tracker-list">
          <label v-for="a in filteredAgents" :key="String(a.id)" class="tracker-item">
            <input
              type="checkbox"
              :checked="trackedSet.has(String(a.id))"
              @change="toggleTrack(String(a.id))"
            />
            <span class="dot" :style="{ background: colorForAgent(String(a.id)) }"></span>
            <span class="tracker-name">{{ npcName(a) }}</span>
            <span class="tracker-loc">@{{ roomLabel(currentLocation(String(a.id))) }}</span>
          </label>
          <div v-if="!filteredAgents.length" class="empty-small">
            {{ lang.t('无匹配的 NPC', 'no NPC matched') }}
          </div>
        </div>
      </div>

      <button class="ctrl-btn topright" @click="resetView">
        {{ lang.t('重置视图', 'Reset View') }}
      </button>
    </div>

    <aside class="scene-side">
      <RoomHeatPanel
        :rooms="rooms"
        :world-agents="world.worldSnapshot?.agents || null"
        :highlight-uid="selectedUid"
        :filter-agent-ids="trackedAgents"
        @select-room="onSelectNode"
      />

      <div class="panel-header">
        <h2>{{ lang.t('房间详情', 'Room Detail') }}</h2>
      </div>
      <div class="panel-content" v-if="!selected">
        <div class="placeholder">
          {{ lang.t('点击图谱中的房间查看详情。', 'Click a room to inspect.') }}
        </div>
      </div>
      <div class="panel-content" v-else>
        <div class="room-name">{{ selected.name }}</div>
        <div class="kv"><span class="k">UID</span><span class="v mono">{{ selected.uid }}</span></div>
        <div class="kv"><span class="k">{{ lang.t('容量', 'Containment') }}</span>
          <span class="v">{{ selected.containment }}</span></div>
        <div class="kv"><span class="k">{{ lang.t('坐标', 'Position') }}</span>
          <span class="v mono">{{ (selected.position || []).join(', ') }}</span></div>

        <div class="section-title">{{ lang.t('标签', 'Tags') }}</div>
        <Chip v-for="t in (selected.tag || [])" :key="t" variant="default">{{ t }}</Chip>

        <div class="section-title">{{ lang.t('描述', 'Description') }}</div>
        <div class="desc">{{ selected.description }}</div>

        <div class="section-title" v-if="(selected.furniture || []).length">
          {{ lang.t('家具', 'Furniture') }}
        </div>
        <div v-if="(selected.furniture || []).length" class="kv-block">
          <div v-for="f in selected.furniture" :key="f.name" class="kv">
            <span class="k">{{ f.name }}</span>
            <span class="v">×{{ f.num }}</span>
          </div>
        </div>

        <div class="section-title">{{ lang.t('相邻房间', 'Adjacent') }}</div>
        <Chip
          v-for="uid in (selected.adjacent || [])"
          :key="uid"
          variant="people"
          :clickable="true"
          @click="jumpToRoom(uid)"
        >
          {{ roomLabel(uid) }}
        </Chip>

        <div class="section-title">{{ lang.t('当前在此的 NPC', 'NPCs currently here') }}</div>
        <Chip
          v-for="a in agentsHere"
          :key="String(a.id)"
          variant="people"
          :clickable="true"
          @click="$router.push(`/agent/${a.id}`)"
        >
          {{ npcName(a) }}
        </Chip>
        <div v-if="!agentsHere.length" class="empty">
          {{ lang.t('（暂无 NPC 在此）', '(no NPC here)') }}
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
import RoomHeatPanel from '@/components/RoomHeatPanel.vue';
import Chip from '@/components/Chip.vue';
import { useWorldStore } from '@/stores/world';
import { useAgentsStore } from '@/stores/agents';
import { useLangStore } from '@/stores/lang';
import type { Room, AgentLite } from '@/api/endpoints';

const lang = useLangStore();
const world = useWorldStore();
const agents = useAgentsStore();

const graphRef = ref<InstanceType<typeof NetworkGraph> | null>(null);
const selectedUid = ref<string | null>(null);

// ---- NPC tracking state ----
const trackedAgents = ref<string[]>([]);  // ordered list of agent ids
const trackedSet = computed(() => new Set(trackedAgents.value));
const filterText = ref('');

const rooms = computed<Room[]>(() => world.sceneGraph?.rooms || []);
const roomMap = computed<Record<string, Room>>(() => {
  const m: Record<string, Room> = {};
  for (const r of rooms.value) m[r.uid] = r;
  return m;
});
const selected = computed<Room | null>(() => selectedUid.value ? roomMap.value[selectedUid.value] || null : null);

/* Tag-based color palette (lightweight). */
const TAG_COLOR: Record<string, string> = {
  'study':      '#42A5F5',
  'social':     '#66BB6A',
  'leisure':    '#26C6DA',
  'daily life': '#FFA726',
  'fitness':    '#EF5350',
};
function colorOf(tag?: string[]): string {
  if (!tag || !tag.length) return '#90caf9';
  return TAG_COLOR[tag[0]] || '#90caf9';
}

const vNodes = computed(() =>
  rooms.value.map(r => ({
    id: r.uid,
    label: r.name,
    title: `${r.name} · ${r.uid}\n${r.description}`,
    color: { background: colorOf(r.tag), border: '#0a0e17' },
    value: r.containment || 1,
  }))
);
const vEdges = computed(() => {
  const seen = new Set<string>();
  const out: any[] = [];
  for (const r of rooms.value) {
    for (const a of (r.adjacent || [])) {
      const key = [r.uid, a].sort().join('|');
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ from: r.uid, to: a, color: { color: '#1e2a45', opacity: 0.7 } });
    }
  }
  return out;
});

const opts = {
  nodes: { shape: 'dot', size: 22, font: { size: 13, color: '#cfd8dc' } },
  physics: {
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -80,
      springLength: 220,
      springConstant: 0.05,
    },
    stabilization: { iterations: 250 },
  },
};

// ---- NPC tracking: derive nodes + edges to merge into the graph ----
function colorForAgent(id: string): string {
  // stable HSL hash so the same NPC always gets the same hue
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360}, 70%, 60%)`;
}

function currentLocation(id: string): string | null {
  const snap = (world.worldSnapshot?.agents) as any;
  if (snap && snap[id]) return snap[id].location_uid || null;
  const a = agents.list.find(x => String(x.id) === id);
  return a ? (a.location_uid || null) : null;
}

const vNpcNodes = computed(() => {
  const out: any[] = [];
  for (const id of trackedAgents.value) {
    const loc = currentLocation(id);
    if (!loc || !roomMap.value[loc]) continue;
    const a = agents.list.find(x => String(x.id) === id);
    const label = a ? npcName(a) : id;
    out.push({
      id: `npc:${id}`,
      label,
      title: `${label}\n@${roomMap.value[loc]?.name || loc}`,
      shape: 'dot',
      size: 12,
      color: { background: colorForAgent(id), border: '#0a0e17' },
      font: { color: '#fff', size: 11 },
      borderWidth: 2,
      // mass < 1 makes the NPC node "orbit" the room without dragging it.
      mass: 0.4,
    });
  }
  return out;
});
const vNpcEdges = computed(() => {
  const out: any[] = [];
  for (const id of trackedAgents.value) {
    const loc = currentLocation(id);
    if (!loc || !roomMap.value[loc]) continue;
    out.push({
      id: `npc-edge:${id}`,
      from: `npc:${id}`,
      to: loc,
      dashes: true,
      color: { color: colorForAgent(id), opacity: 0.55 },
      width: 1.5,
      length: 90,
    });
  }
  return out;
});
const vNodesAll = computed(() => [...vNodes.value, ...vNpcNodes.value]);
const vEdgesAll = computed(() => [...vEdges.value, ...vNpcEdges.value]);

const filteredAgents = computed<AgentLite[]>(() => {
  const q = filterText.value.trim().toLowerCase();
  const list = agents.list || [];
  if (!q) return list;
  return list.filter(a => {
    const id = String(a.id).toLowerCase();
    const name = (a.name || '').toLowerCase();
    const ne = ((a as any).name_en || '').toLowerCase();
    return id.includes(q) || name.includes(q) || ne.includes(q);
  });
});

function toggleTrack(id: string) {
  const i = trackedAgents.value.indexOf(id);
  if (i >= 0) trackedAgents.value.splice(i, 1);
  else trackedAgents.value.push(id);
}
function trackAll() {
  trackedAgents.value = (agents.list || []).map(a => String(a.id));
}
function trackNone() { trackedAgents.value = []; }

function shortTime(iso: string): string {
  // 2026-05-26T07:35:00 → 05-26 07:35
  try {
    return iso.replace('T', ' ').slice(5, 16);
  } catch {
    return iso;
  }
}

function onSelectNode(nodeId: string) {
  // virtual NPC nodes start with "npc:" — clicking one routes to that agent.
  if (nodeId.startsWith('npc:')) {
    const aid = nodeId.slice(4);
    // navigate to AgentDetailView
    (window as any).__lastClickedAgent = aid;
    window.location.hash = `#/agent/${aid}`;
    return;
  }
  selectedUid.value = nodeId;
}
function jumpToRoom(uid: string) {
  selectedUid.value = uid;
  graphRef.value?.focus?.(uid);
}
function resetView() {
  graphRef.value?.fit?.();
}
function roomLabel(uid: string): string {
  return roomMap.value[uid]?.name || uid;
}

const agentsHere = computed<AgentLite[]>(() => {
  const uid = selectedUid.value;
  if (!uid) return [];
  // Prefer the world snapshot if loaded; fall back to agents.list.
  const snap = (world.worldSnapshot?.agents || []) as any[];
  const here = snap.length
    ? snap.filter(a => a.location_uid === uid)
    : agents.list.filter(a => a.location_uid === uid);
  // Hydrate names from agents.list by id when needed.
  return here.map(a => ({
    ...(agents.list.find(b => String(b.id) === String(a.id)) || {}),
    ...a,
  })) as AgentLite[];
});
function npcName(a: AgentLite): string {
  if (lang.lang === 'en') return (a as any).name_en || a.name || String(a.id);
  return a.name || (a as any).name_en || String(a.id);
}

onMounted(async () => {
  await Promise.all([
    world.loadScene(),
    world.loadWorld(),
    agents.loadList(),
  ]);
  // Poll world snapshot every 3s so tracked NPC nodes re-attach when an NPC
  // changes room (vis-network animates the edge re-layout).
  world.startPolling(3000);
});
onBeforeUnmount(() => {
  world.stopPolling();
});
</script>

<style scoped>
.scene-page { display: flex; height: 100%; }
.scene-graph { flex: 1; position: relative; min-width: 0; }
.scene-side {
  width: 380px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.scene-side > .rhp {
  border-bottom: 1px solid var(--border-soft);
  background: var(--bg-elevated);
}

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
}
.stats b { color: var(--accent-warn); margin-left: 4px; }

.topright { position: absolute; top: 16px; right: 16px; }

.panel-header {
  padding: 14px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.panel-header h2 { font-size: 16px; color: var(--accent-primary); }
.panel-content { padding: 14px 18px; flex: 1; overflow-y: auto; }
.placeholder {
  color: var(--text-disabled);
  text-align: center;
  padding: 30px 8px;
}

.room-name {
  color: var(--accent-warm-soft);
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
}
.kv { display: flex; gap: 6px; font-size: 12.5px; color: var(--text-secondary); margin: 3px 0; }
.kv .k { color: var(--text-very-dim); min-width: 70px; }
.kv .v { color: var(--text-secondary); }
.kv-block { background: var(--bg-card); padding: 6px 10px; border-radius: 6px; margin-top: 4px; }
.mono { font-family: Consolas, monospace; font-size: 11px; }
.desc {
  background: var(--bg-card);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.empty { color: var(--text-disabled); font-size: 12px; padding: 4px 0; }

/* ---- NPC tracker panel ---- */
.tracker-panel {
  position: absolute;
  bottom: 16px; left: 16px;
  width: 280px;
  max-height: 50vh;
  display: flex; flex-direction: column;
  background: rgba(18,24,43,0.94);
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.35);
  z-index: 5;
}
.tracker-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.tracker-header strong { color: var(--accent-primary); font-size: 13px; }
.tracker-actions { display: flex; gap: 6px; }
.micro-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.micro-btn:hover { background: var(--bg-elevated); color: var(--accent-primary); }
.tracker-filter {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  margin-bottom: 6px;
  outline: none;
  box-sizing: border-box;
}
.tracker-list { overflow-y: auto; max-height: 30vh; }
.tracker-item {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 0;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.tracker-item:hover { color: var(--text-primary); }
.tracker-item .dot {
  width: 10px; height: 10px; border-radius: 50%;
  display: inline-block;
}
.tracker-name { flex: 1; }
.tracker-loc { color: var(--text-very-dim); font-size: 10.5px; }
.sim-clock { color: var(--accent-warm-soft); margin-left: auto; }
.empty-small { color: var(--text-disabled); font-size: 11px; padding: 4px; text-align: center; }
</style>
