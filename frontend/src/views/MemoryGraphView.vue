<!--
  Memory triplet narrative graph — NPC-centric view.

  Rendering rules:
  - Nodes are ONLY NPCs (one per agent appearing in any triplet).
  - Edges encode NPC↔NPC interactions, aggregated PER (subject, object) PAIR
    (a single edge accumulates all predicates between the two NPCs, with the
    full breakdown shown in the side panel when the edge is clicked).
  - Self-events (subject is an NPC, object isn't) are attached to that NPC and
    visible in the side panel when the NPC is selected.

  Performance notes:
  - Physics is auto-disabled once stabilisation finishes; without this every
    selection re-ran the force solver.
  - Selection styling is applied imperatively via `graphRef.updateNodes` so
    clicks don't invalidate the reactive `vNodes` array and trigger a full
    diff/update for every node.
  - Edge labels are only painted on the top-K (and the selected NPC's
    incident) edges — vis-network's per-edge label paint was the dominant
    cost when every edge always carried a label.
-->
<template>
  <div class="mg">
    <div class="mg-graph">
      <NetworkGraph
        ref="graphRef"
        :nodes="vNodes"
        :edges="vEdges"
        :options="opts"
        @select-node="onSelectNpc"
        @select-edge="onSelectEdge"
        @deselect="onDeselect"
        @ready="onReady"
      />
      <div class="stats">
        <span>{{ lang.t('NPC 节点', 'NPC nodes') }} <b>{{ vNodes.length }}</b></span>
        <span>{{ lang.t('互动边', 'Interaction edges') }} <b>{{ pairEdges.length }}</b></span>
        <span>{{ lang.t('自身事件', 'Self-events') }} <b>{{ totalSelfEvents }}</b></span>
      </div>
      <div class="topright">
        <label class="ctrl-chip" :title="lang.t('显示标签的高频边数量', 'How many edges show a label')">
          {{ lang.t('显标签', 'Labels') }}
          <input
            type="range" min="0" max="30" step="1"
            v-model.number="labelTopK"
          />
          <b>{{ labelTopK }}</b>
        </label>
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
        <!-- Header switches between 3 modes: global / NPC / Edge -->
        <h2 v-if="!selectedNpc && !selectedEdge">
          {{ lang.t('NPC 记忆叙事', 'NPC Memory Narratives') }}
        </h2>
        <h2 v-else-if="selectedNpc">
          <span class="dot-mini" :style="{ background: colorForAgent(selectedNpc) }"></span>
          {{ entityLabel(selectedNpc) }}
        </h2>
        <h2 v-else-if="selectedEdge">
          <span class="edge-mini" />
          {{ entityLabel(selectedEdge.from) }}
          <span class="arrow">→</span>
          {{ entityLabel(selectedEdge.to) }}
        </h2>
        <button
          v-if="selectedNpc || selectedEdge"
          class="micro-btn"
          @click="clearSelection"
        >
          {{ lang.t('返回全部', 'Back') }}
        </button>
      </div>

      <div class="panel-content">
        <!-- ============= No selection: global view ============= -->
        <template v-if="!selectedNpc && !selectedEdge">
          <div class="hint">
            {{ lang.t(
              '节点 = NPC；边 = 两个 NPC 之间的所有互动（已合并）。\n点击节点查看其互动与自身事件；点击边查看完整事件分解。',
              'Nodes = NPCs. Edges = all interactions between two NPCs (aggregated).\nClick a node for its interactions & self-events; click an edge for the full breakdown.'
            ) }}
          </div>

          <h3 class="sec">{{ lang.t('🔗 NPC 互动 (Top)', '🔗 NPC interactions (top)') }}</h3>
          <div v-if="!pairEdges.length" class="placeholder">
            {{ lang.t('暂无 NPC ↔ NPC 互动。', 'No NPC↔NPC interactions yet.') }}
          </div>
          <div
            v-for="(e, idx) in topPairEdges"
            :key="`pair:${e.from}|${e.to}|${idx}`"
            class="pair-card"
            :style="{ borderLeftColor: toneColor(e.tone) }"
            @click="selectEdgeByPair(e)"
          >
            <div class="pair-line">
              <span class="subj">{{ entityLabel(e.from) }}</span>
              <span class="arrow">→</span>
              <span class="obj">{{ entityLabel(e.to) }}</span>
              <span class="cnt">×{{ e.total }}</span>
            </div>
            <div class="pair-preds">
              <span
                v-for="(p, pi) in e.predicates.slice(0, 4)"
                :key="pi"
                class="pred-pill"
              >
                {{ p.predicate }}<small v-if="p.count > 1">×{{ p.count }}</small>
              </span>
              <span v-if="e.predicates.length > 4" class="more">+{{ e.predicates.length - 4 }}</span>
            </div>
          </div>
        </template>

        <!-- ============= NPC selected ============= -->
        <template v-else-if="selectedNpc">
          <h3 class="sec">{{ lang.t('🤝 与他人互动', '🤝 Interactions with others') }}</h3>
          <div v-if="!npcEdges.length" class="placeholder">
            {{ lang.t('（暂无）', '(none)') }}
          </div>
          <div
            v-for="(e, idx) in npcEdges"
            :key="`npce:${e.from}|${e.to}|${idx}`"
            class="pair-card"
            :style="{ borderLeftColor: toneColor(e.tone) }"
            @click="selectEdgeByPair(e)"
          >
            <div class="pair-line">
              <span class="subj">{{ entityLabel(e.from) }}</span>
              <span class="arrow">→</span>
              <span class="obj">{{ entityLabel(e.to) }}</span>
              <span class="cnt">×{{ e.total }}</span>
            </div>
            <div class="pair-preds">
              <span
                v-for="(p, pi) in e.predicates.slice(0, 4)"
                :key="pi"
                class="pred-pill"
              >
                {{ p.predicate }}<small v-if="p.count > 1">×{{ p.count }}</small>
              </span>
              <span v-if="e.predicates.length > 4" class="more">+{{ e.predicates.length - 4 }}</span>
            </div>
          </div>

          <h3 class="sec">{{ lang.t('📋 自身事件', '📋 Self-events') }}</h3>
          <div v-if="!npcSelfEvents.length" class="placeholder">
            {{ lang.t('（暂无自身事件）', '(no self-events)') }}
          </div>
          <div
            v-for="(t, i) in npcSelfEvents"
            :key="`self:${i}`"
            class="triplet self"
            :style="{ borderLeftColor: toneColor(t.tone) }"
          >
            <div class="line">
              <span class="pred">{{ t.predicate }}</span>
              <span class="obj">{{ entityLabel(t.object) }}</span>
            </div>
            <div v-if="t.location_uid" class="loc">@{{ entityLabel(t.location_uid) }}</div>
          </div>
        </template>

        <!-- ============= Edge selected ============= -->
        <template v-else-if="selectedEdge">
          <div class="edge-summary">
            <div class="edge-headline">
              <strong>{{ entityLabel(selectedEdge.from) }}</strong>
              <span class="arrow big">→</span>
              <strong>{{ entityLabel(selectedEdge.to) }}</strong>
            </div>
            <div class="edge-meta">
              <span>{{ lang.t('总互动', 'Total interactions') }} <b>×{{ selectedEdge.total }}</b></span>
              <span>{{ lang.t('谓词种类', 'Predicate kinds') }} <b>{{ selectedEdge.predicates.length }}</b></span>
              <span v-if="selectedEdge.location_uid">
                {{ lang.t('最近地点', 'Last location') }}
                <b>{{ entityLabel(selectedEdge.location_uid) }}</b>
              </span>
            </div>
          </div>

          <h3 class="sec">{{ lang.t('📚 互动分解 (按谓词聚合)', '📚 Breakdown (by predicate)') }}</h3>
          <div
            v-for="(p, i) in selectedEdge.predicates"
            :key="`pe:${i}`"
            class="triplet"
            :style="{ borderLeftColor: toneColor(p.tone) }"
          >
            <div class="line">
              <span class="pred">{{ p.predicate }}</span>
              <span v-if="p.count > 1" class="cnt">×{{ p.count }}</span>
            </div>
            <div v-if="p.location_uid" class="loc">@{{ entityLabel(p.location_uid) }}</div>
          </div>

          <div class="edge-jump">
            <button class="micro-btn" @click="selectedNpc = selectedEdge!.from; selectedEdge = null;">
              {{ lang.t('查看', 'Open') }} {{ entityLabel(selectedEdge.from) }}
            </button>
            <button class="micro-btn" @click="selectedNpc = selectedEdge!.to; selectedEdge = null;">
              {{ lang.t('查看', 'Open') }} {{ entityLabel(selectedEdge.to) }}
            </button>
          </div>
        </template>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import type { Network } from 'vis-network/standalone';
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

interface PredicateAgg {
  predicate: string;
  count: number;
  tone?: string;
  location_uid?: string;
}

interface PairEdge {
  /** Stable id for vis-network so node-selection styling updates are cheap. */
  id: string;
  from: string;
  to: string;
  total: number;
  /** Predicate breakdown, sorted by frequency desc. */
  predicates: PredicateAgg[];
  /** Most-common predicate label (used as the on-canvas summary label). */
  topPredicate: string;
  /** Modal tone across predicates. */
  tone?: string;
  /** Most-recent location attached to any of the predicates. */
  location_uid?: string;
}

const triplets = ref<Triplet[]>([]);
const graphRef = ref<InstanceType<typeof NetworkGraph> | null>(null);
const selectedNpc = ref<string | null>(null);
const selectedEdge = ref<PairEdge | null>(null);
const labelTopK = ref<number>(8);
let netInstance: Network | null = null;

/** Stable warm-tone color per agent id (matches the scene-graph palette). */
function colorForAgent(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const hue = h % 60;
  return `hsl(${hue}, 85%, 62%)`;
}

function entityLabel(id: string): string {
  if (!id) return '?';
  const a = agents.list.find(x => String(x.id) === id);
  if (a) {
    if (lang.lang === 'en') return (a as any).name_en || a.name || id;
    return a.name || (a as any).name_en || id;
  }
  if (/^npc\d+_/i.test(id)) return id.split('_').slice(1).join('_') || id;
  return id;
}

function isNpc(id: string): boolean {
  if (!id) return false;
  if (agents.list.some(a => String(a.id) === id)) return true;
  return /^npc\d+_/i.test(id);
}

const TONE_MAP: Record<string, string> = {
  warm:'#ffa726', tense:'#ef5350', focused:'#26c6da', casual:'#78909c',
  curious:'#ce93d8', gentle:'#a5d6a7', playful:'#fff176', decisive:'#ff8a65',
};
function toneColor(t?: string): string { return (t && TONE_MAP[t]) || '#42a5f5'; }
function modeTone(preds: PredicateAgg[]): string | undefined {
  const tally = new Map<string, number>();
  for (const p of preds) {
    if (!p.tone) continue;
    tally.set(p.tone, (tally.get(p.tone) || 0) + p.count);
  }
  let best: string | undefined;
  let bestN = -1;
  for (const [k, v] of tally) if (v > bestN) { best = k; bestN = v; }
  return best;
}

/* ===================================================================
   Triplet analysis: aggregate NPC↔NPC edges per PAIR (not per predicate)
   plus per-NPC self-events.
   =================================================================== */
const analysis = computed(() => {
  const npcSet = new Set<string>();
  const pairMap = new Map<string, { predMap: Map<string, PredicateAgg>; lastLoc?: string }>();
  const selfEvents = new Map<string, Triplet[]>();

  for (const t of triplets.value) {
    const s = t.subject;
    const o = t.object;
    const sNpc = isNpc(s);
    const oNpc = isNpc(o);

    if (sNpc && oNpc && s !== o) {
      npcSet.add(s); npcSet.add(o);
      const pairKey = `${s}|${o}`;
      let slot = pairMap.get(pairKey);
      if (!slot) { slot = { predMap: new Map() }; pairMap.set(pairKey, slot); }
      const pAgg = slot.predMap.get(t.predicate);
      if (pAgg) {
        pAgg.count++;
        if (t.tone) pAgg.tone = t.tone;
        if (t.location_uid) pAgg.location_uid = t.location_uid;
      } else {
        slot.predMap.set(t.predicate, {
          predicate: t.predicate, count: 1,
          tone: t.tone, location_uid: t.location_uid,
        });
      }
      if (t.location_uid) slot.lastLoc = t.location_uid;
    } else if (sNpc) {
      npcSet.add(s);
      const arr = selfEvents.get(s) || [];
      arr.push(t);
      selfEvents.set(s, arr);
    } else if (oNpc) {
      npcSet.add(o);
      const arr = selfEvents.get(o) || [];
      arr.push(t);
      selfEvents.set(o, arr);
    }
  }

  const edges: PairEdge[] = [];
  for (const [key, slot] of pairMap) {
    const [from, to] = key.split('|');
    const preds = [...slot.predMap.values()].sort((a, b) => b.count - a.count);
    const total = preds.reduce((acc, p) => acc + p.count, 0);
    edges.push({
      id: `pe:${from}|${to}`,
      from, to, total,
      predicates: preds,
      topPredicate: preds[0]?.predicate || '',
      tone: modeTone(preds),
      location_uid: slot.lastLoc,
    });
  }
  edges.sort((a, b) => b.total - a.total);

  return { npcSet, edges, selfEvents };
});

const pairEdges = computed(() => analysis.value.edges);
const totalSelfEvents = computed(() => {
  let n = 0;
  for (const arr of analysis.value.selfEvents.values()) n += arr.length;
  return n;
});
const topPairEdges = computed(() => pairEdges.value.slice(0, 40));

const npcEdges = computed<PairEdge[]>(() => {
  if (!selectedNpc.value) return [];
  return pairEdges.value
    .filter(e => e.from === selectedNpc.value || e.to === selectedNpc.value);
});
const npcSelfEvents = computed<Triplet[]>(() => {
  if (!selectedNpc.value) return [];
  return analysis.value.selfEvents.get(selectedNpc.value) || [];
});

/* ===================================================================
   vis-network nodes & edges.
   IMPORTANT: vNodes does NOT depend on selectedNpc/selectedEdge.
   Selection-driven styling is applied imperatively via updateNodes()
   so that clicks do not invalidate the whole reactive array.
   =================================================================== */
function buildNpcTitle(npcId: string, selfs: Triplet[]): string {
  const name = entityLabel(npcId);
  if (!selfs.length) return name;
  const head = `${name} · ${selfs.length} self-events`;
  const body = selfs.slice(-8).map(t =>
    `· ${t.predicate} ${entityLabel(t.object)}`
  ).join('\n');
  const more = selfs.length > 8 ? `\n…+${selfs.length - 8}` : '';
  return `${head}\n${body}${more}`;
}

const vNodes = computed(() => {
  const out: any[] = [];
  for (const npcId of analysis.value.npcSet) {
    const selfs = analysis.value.selfEvents.get(npcId) || [];
    const baseColor = colorForAgent(npcId);
    out.push({
      id: npcId,
      label: entityLabel(npcId) + (selfs.length ? `  📋${selfs.length}` : ''),
      title: buildNpcTitle(npcId, selfs),
      shape: 'dot',
      size: 18,
      color: {
        background: baseColor,
        border: '#1a0d00',
        highlight: { background: baseColor, border: '#FFFFFF' },
      },
      borderWidth: 1.5,
      font: { color: '#fff', size: 12, strokeWidth: 2, strokeColor: '#0a0e17' },
    });
  }
  return out;
});

/** Set of pair-edge ids that should carry a label. Recomputes only when the
 *  underlying edges or the labelTopK slider changes — not on selection. */
const labelEdgeIds = computed(() => {
  const set = new Set<string>();
  for (let i = 0; i < Math.min(labelTopK.value, pairEdges.value.length); i++) {
    set.add(pairEdges.value[i].id);
  }
  return set;
});

const vEdges = computed(() => pairEdges.value.map(e => {
  const showLabel = labelEdgeIds.value.has(e.id);
  return {
    id: e.id,
    from: e.from,
    to: e.to,
    label: showLabel
      ? (e.predicates.length > 1
          ? `${e.topPredicate}+${e.predicates.length - 1}  ×${e.total}`
          : `${e.topPredicate} ×${e.total}`)
      : undefined,
    width: 1 + Math.min(5, Math.log2(e.total + 1)),
    arrows: { to: { enabled: true, scaleFactor: 0.55 } },
    color: { color: toneColor(e.tone), opacity: 0.7 },
    font: showLabel
      ? { color: '#cfd8dc', size: 10, strokeWidth: 0, align: 'middle' }
      : undefined,
    smooth: { enabled: true, type: 'continuous', roundness: 0.15 },
  };
}));

/* ===================================================================
   Imperative selection highlight — avoids invalidating vNodes.
   =================================================================== */
const HIGHLIGHT_BORDER = '#FFD54F';
const NORMAL_BORDER = '#1a0d00';

function applyNodeHighlights() {
  const net = graphRef.value;
  if (!net) return;
  // Build a minimal updates payload for just the touched nodes.
  const touched: any[] = [];
  for (const npcId of analysis.value.npcSet) {
    const isSelNpc = selectedNpc.value === npcId;
    const isOnEdge = !!selectedEdge.value &&
      (selectedEdge.value.from === npcId || selectedEdge.value.to === npcId);
    const highlight = isSelNpc || isOnEdge;
    touched.push({
      id: npcId,
      size: isSelNpc ? 26 : 18,
      borderWidth: highlight ? 3 : 1.5,
      color: {
        background: colorForAgent(npcId),
        border: highlight ? HIGHLIGHT_BORDER : NORMAL_BORDER,
        highlight: { background: colorForAgent(npcId), border: '#FFFFFF' },
      },
    });
  }
  net.updateNodes(touched);
}

watch([selectedNpc, selectedEdge], () => applyNodeHighlights());

const opts = {
  edges: { arrows: { to: { enabled: true, scaleFactor: 0.55 } } },
  interaction: {
    hover: true,
    tooltipDelay: 200,
    selectConnectedEdges: false,
    hideEdgesOnDrag: true,   // big perf win while dragging viewport
    hideEdgesOnZoom: true,   // ditto for zoom
  },
  physics: {
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -45,
      centralGravity: 0.012,
      springLength: 140,
      springConstant: 0.05,
      damping: 0.5,
    },
    // Cap initial layout cost; we also disable physics in `onReady` once it
    // stabilises so subsequent ticks/clicks don't re-run the force solver.
    stabilization: { iterations: 180, fit: true },
  },
};

function onReady(net: Network) {
  netInstance = net;
  net.once('stabilizationIterationsDone', () => {
    net.setOptions({ physics: { enabled: false } });
    applyNodeHighlights();
  });
}

/* ===================================================================
   Selection handlers
   =================================================================== */
function onSelectNpc(id: string) {
  selectedEdge.value = null;
  selectedNpc.value = id;
}
function onSelectEdge(eid: string | number, fromTo: { from: string; to: string }) {
  const e = pairEdges.value.find(x => x.id === String(eid));
  if (e) { selectedNpc.value = null; selectedEdge.value = e; return; }
  // Fallback: locate by from/to (in case ids drifted)
  const e2 = pairEdges.value.find(x => x.from === fromTo.from && x.to === fromTo.to);
  if (e2) { selectedNpc.value = null; selectedEdge.value = e2; }
}
function onDeselect() {
  selectedNpc.value = null;
  selectedEdge.value = null;
}
function clearSelection() {
  selectedNpc.value = null;
  selectedEdge.value = null;
  netInstance?.unselectAll?.();
}
function selectEdgeByPair(e: PairEdge) {
  selectedNpc.value = null;
  selectedEdge.value = e;
  netInstance?.selectEdges?.([e.id]);
}

/* ===================================================================
   Data fetch (REST, one-shot on mount).
   =================================================================== */
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

function resetView() { graphRef.value?.fit?.(); }

onMounted(async () => {
  await reload();
});
</script>

<style scoped>
.mg { display: flex; height: 100%; }
.mg-graph { flex: 1; position: relative; min-width: 0; }
.mg-side {
  width: 380px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
}
.panel-header {
  padding: 14px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.panel-header h2 {
  font-size: 16px; color: var(--accent-primary);
  display: flex; align-items: center; gap: 8px;
  margin: 0;
}
.panel-header h2 .arrow { color: var(--text-very-dim); font-weight: 400; }
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
  display: flex; gap: 8px; align-items: center;
}
.ctrl-chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: rgba(18,24,43,0.92);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 4px 10px;
  font-size: 11.5px;
  color: var(--text-very-dim);
}
.ctrl-chip input[type="range"] { width: 90px; accent-color: var(--accent-warn); }
.ctrl-chip b { color: var(--accent-warn); font-size: 11px; min-width: 18px; text-align: center; }
.ctrl-btn {
  background: var(--bg-card); border: 1px solid var(--border-soft);
  color: var(--text-secondary); border-radius: 8px; cursor: pointer;
  padding: 4px 10px; font-size: 12px;
}
.ctrl-btn:hover { color: var(--accent-primary); background: var(--bg-elevated); }

.hint {
  color: var(--text-very-dim); font-size: 11.5px; margin-bottom: 10px;
  white-space: pre-line; line-height: 1.5;
}
.placeholder { color: var(--text-disabled); font-size: 12px; }

/* Generic triplet (self-events, predicate breakdown rows) */
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
.triplet .cnt  {
  margin-left: 6px;
  color: var(--text-very-dim);
  font-family: Consolas, monospace;
  font-size: 10.5px;
}
.triplet .loc  {
  color: var(--text-very-dim);
  font-family: Consolas, monospace;
  font-size: 10.5px;
  margin-top: 2px;
}
.triplet.self { background: rgba(255,193,7,0.04); border-left-width: 2px; }

/* Pair card — used in global view and NPC view to summarise an edge */
.pair-card {
  background: var(--bg-card);
  padding: 8px 10px;
  border-left: 3px solid var(--accent-active);
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: background 0.12s ease;
}
.pair-card:hover { background: var(--bg-elevated); }
.pair-line {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: 12.5px;
}
.pair-line .subj { color: var(--accent-primary); font-weight: 600; }
.pair-line .obj  { color: var(--accent-good-soft); font-weight: 600; }
.pair-line .arrow { color: var(--text-very-dim); font-size: 12px; }
.pair-line .cnt {
  margin-left: auto;
  color: var(--accent-warn);
  font-family: Consolas, monospace;
  font-size: 11.5px;
}
.pair-preds {
  margin-top: 4px;
  display: flex; flex-wrap: wrap; gap: 4px;
}
.pred-pill {
  background: rgba(66,165,245,0.10);
  border: 1px solid rgba(66,165,245,0.25);
  color: var(--text-secondary);
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 8px;
}
.pred-pill small { color: var(--text-very-dim); margin-left: 2px; }
.pair-preds .more {
  color: var(--text-very-dim); font-size: 10.5px;
  padding: 1px 4px;
}

/* Edge-selected detail */
.edge-summary {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.edge-headline {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px;
}
.edge-headline strong { color: var(--accent-primary); }
.edge-headline .arrow.big { color: var(--accent-warn); font-size: 16px; }
.edge-meta {
  display: flex; flex-wrap: wrap; gap: 10px;
  margin-top: 8px;
  font-size: 11.5px; color: var(--text-very-dim);
}
.edge-meta b { color: var(--accent-warn); margin-left: 3px; }
.edge-jump {
  display: flex; gap: 8px; margin-top: 12px;
}

.dot-mini {
  width: 12px; height: 12px; border-radius: 50%;
  display: inline-block;
  border: 1px solid #0a0e17;
}
.edge-mini {
  width: 18px; height: 2px; background: var(--accent-warn);
  display: inline-block;
  vertical-align: middle;
}
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

.sec {
  font-size: 12px;
  color: var(--accent-primary);
  margin: 12px 0 6px;
  letter-spacing: 0.4px;
}
</style>
