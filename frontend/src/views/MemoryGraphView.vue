<!--
  Memory triplet narrative graph.
  Aggregates triplets from all NPCs (subject → object edges, predicate as label).
  Tone-colors the edges.
-->
<template>
  <div class="mg">
    <div class="mg-graph">
      <NetworkGraph
        ref="graphRef"
        :nodes="vNodes"
        :edges="vEdges"
        :options="opts"
        @select-node="onSelectSubject"
      />
      <div class="stats">
        <span>{{ lang.t('节点', 'Nodes') }} <b>{{ vNodes.length }}</b></span>
        <span>{{ lang.t('三元组', 'Triplets') }} <b>{{ vEdges.length }}</b></span>
      </div>
      <div class="topright">
        <button class="ctrl-btn" @click="reload">
          {{ lang.t('刷新', 'Refresh') }}
        </button>
        <button class="ctrl-btn" @click="resetView">
          {{ lang.t('重置视图', 'Reset View') }}
        </button>
      </div>
    </div>

    <aside class="mg-side">
      <div class="panel-header">
        <h2>{{ lang.t('三元组叙事', 'Triplet Narratives') }}</h2>
      </div>
      <div class="panel-content">
        <div class="hint">
          {{ lang.t(
            '聚合所有 NPC 的记忆三元组（subject → predicate → object）。基调以左侧色条标识。',
            'Aggregated triplets across all NPCs. Left-border color = tone.'
          ) }}
        </div>
        <div v-if="!triplets.length" class="placeholder">
          {{ lang.t('暂无三元组。', 'No triplets yet.') }}
        </div>
        <div v-for="(t, i) in triplets" :key="i" class="triplet" :style="{ borderLeftColor: toneColor(t.tone) }">
          <div class="line">
            <span class="subj">{{ t.subject }}</span>
            <span class="pred"> {{ t.predicate }} </span>
            <span class="obj">{{ t.object }}</span>
          </div>
          <div v-if="t.location_uid" class="loc">@{{ t.location_uid }}</div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
import { useAgentsStore } from '@/stores/agents';
import { useLangStore } from '@/stores/lang';
import { api } from '@/api/endpoints';
import { mockAgentMemory } from '@/mock/data';

const lang = useLangStore();
const agents = useAgentsStore();

interface Triplet {
  subject: string;
  predicate: string;
  object: string;
  tone?: string;
  location_uid?: string;
}

const triplets = ref<Triplet[]>([]);
const graphRef = ref<InstanceType<typeof NetworkGraph> | null>(null);

const vNodes = computed(() => {
  const nodes = new Map<string, any>();
  for (const t of triplets.value) {
    if (t.subject && !nodes.has(t.subject)) {
      nodes.set(t.subject, { id: t.subject, label: t.subject, color: { background: '#1a2240', border: '#90caf9' } });
    }
    if (t.object && !nodes.has(t.object)) {
      nodes.set(t.object, { id: t.object, label: t.object, color: { background: '#1a2240', border: '#a5d6a7' } });
    }
  }
  return Array.from(nodes.values());
});

const TONE_MAP: Record<string, string> = {
  warm:'#ffa726', tense:'#ef5350', focused:'#26c6da', casual:'#78909c',
  curious:'#ce93d8', gentle:'#a5d6a7', playful:'#fff176', decisive:'#ff8a65',
};
function toneColor(t?: string): string { return (t && TONE_MAP[t]) || '#42a5f5'; }

const vEdges = computed(() =>
  triplets.value.map((t, i) => ({
    id: i,
    from: t.subject,
    to: t.object,
    label: t.predicate,
    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
    color: { color: toneColor(t.tone), opacity: 0.8 },
  }))
);

const opts = {
  edges: { arrows: { to: { enabled: true, scaleFactor: 0.6 } } },
  physics: { stabilization: { iterations: 250 } },
};

async function reload() {
  triplets.value = [];
  if (!agents.list.length) await agents.loadList();
  const ids = agents.list.map(a => String(a.id));
  // Cap how many we hit so we don't spam the backend on a 60-NPC build.
  const cap = Math.min(ids.length, 30);
  const out: Triplet[] = [];
  for (let i = 0; i < cap; i++) {
    const id = ids[i];
    try {
      const m = await api.agentMemory(id);
      const g = (m?.graph || []) as any[];
      for (const t of g) {
        if (!t || (!t.subject && !t.object)) continue;
        out.push({
          subject: String(t.subject || '?'),
          predicate: String(t.predicate || ''),
          object: String(t.object || '?'),
          tone: t.tone,
          location_uid: t.location_uid,
        });
      }
    } catch {
      // backend down → mock; only hit mock once
      const m = mockAgentMemory(id) as any;
      for (const t of (m.graph || [])) {
        out.push({
          subject: String(t.subject || '?'),
          predicate: String(t.predicate || ''),
          object: String(t.object || '?'),
          tone: t.tone,
        });
      }
      break;
    }
  }
  triplets.value = out;
}

function onSelectSubject(_id: string) { /* could route to NPC detail in future */ }
function resetView() { graphRef.value?.fit?.(); }

onMounted(async () => {
  await reload();
});
</script>

<style scoped>
.mg { display: flex; height: 100%; }
.mg-graph { flex: 1; position: relative; min-width: 0; }
.mg-side {
  width: 360px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
}
.panel-header {
  padding: 14px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.panel-header h2 { font-size: 16px; color: var(--accent-primary); }
.panel-content { padding: 14px 18px; flex: 1; overflow-y: auto; }

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

.topright {
  position: absolute;
  top: 16px; right: 16px;
  display: flex; gap: 8px;
}

.hint { color: var(--text-very-dim); font-size: 11.5px; margin-bottom: 10px; }
.placeholder { color: var(--text-disabled); font-size: 12px; }

.triplet {
  background: var(--bg-card);
  padding: 6px 10px;
  border-left: 3px solid var(--accent-active);
  border-radius: 4px;
  margin-bottom: 6px;
  font-size: 12px;
}
.triplet .subj { color: var(--accent-primary); font-weight: 600; }
.triplet .pred { color: var(--accent-warn); font-style: italic; }
.triplet .obj  { color: var(--accent-good-soft); font-weight: 600; }
.triplet .loc  {
  color: var(--text-very-dim);
  font-family: Consolas, monospace;
  font-size: 10.5px;
  margin-top: 2px;
}
</style>
