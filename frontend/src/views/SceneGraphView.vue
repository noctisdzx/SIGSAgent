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
        :nodes="vNodes"
        :edges="vEdges"
        :options="opts"
        @select-node="onSelectRoom"
      />
      <div class="stats">
        <span>{{ lang.t('房间', 'Rooms') }}
          <b>{{ rooms.length }}</b></span>
        <span>{{ lang.t('相邻边', 'Adjacencies') }}
          <b>{{ vEdges.length }}</b></span>
      </div>
      <button class="ctrl-btn topright" @click="resetView">
        {{ lang.t('重置视图', 'Reset View') }}
      </button>
    </div>

    <aside class="scene-side">
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
import { computed, onMounted, ref } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
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

function onSelectRoom(uid: string) { selectedUid.value = uid; }
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
</style>
