<!--
  Generic vis-network wrapper.
  Used by RelationView (NPC graph), SceneGraphView (room graph),
  and MemoryGraphView (triplet graph).

  Exposes a `fit()` method via defineExpose for parents that want a "reset zoom" button.
-->
<template>
  <div ref="el" class="network-canvas" />
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { Network } from 'vis-network/standalone';
import type { Data, Options, Node, Edge } from 'vis-network/standalone';

const props = defineProps<{
  nodes: Node[];
  edges: Edge[];
  options?: Options;
}>();

const emit = defineEmits<{
  (e: 'selectNode', id: string): void;
  (e: 'selectEdge', id: string | number, fromTo: { from: string; to: string }): void;
  (e: 'deselect'): void;
  (e: 'ready', net: Network): void;
}>();

const el = ref<HTMLDivElement | null>(null);
let network: Network | null = null;

const DEFAULT_OPTS: Options = {
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
    smooth: { enabled: true, type: 'continuous', roundness: 0.5 },
    arrows: { to: { enabled: false } },
    color: { inherit: false, opacity: 0.7 },
    hoverWidth: 3,
  },
  physics: {
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -40,
      centralGravity: 0.008,
      springLength: 160,
      springConstant: 0.04,
      damping: 0.5,
    },
    stabilization: { iterations: 200 },
  },
  interaction: {
    hover: true,
    tooltipDelay: 100,
    zoomView: true,
    dragView: true,
    multiselect: false,
  },
};

function build() {
  if (!el.value) return;
  const data: Data = { nodes: props.nodes as any, edges: props.edges as any };
  network = new Network(el.value, data, deepMerge(DEFAULT_OPTS, props.options || {}) as Options);

  network.on('click', (params: any) => {
    if (params.nodes?.length) {
      emit('selectNode', String(params.nodes[0]));
      return;
    }
    if (params.edges?.length) {
      const eid = params.edges[0];
      const eRec = (props.edges as any[]).find(e => String(e.id ?? '') === String(eid));
      const from = String(eRec?.from ?? '');
      const to   = String(eRec?.to   ?? '');
      emit('selectEdge', eid, { from, to });
      return;
    }
    emit('deselect');
  });

  emit('ready', network);
}

function deepMerge(a: any, b: any): any {
  if (!b) return a;
  const out: any = { ...a };
  for (const k of Object.keys(b)) {
    if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k])) {
      out[k] = deepMerge(a?.[k] || {}, b[k]);
    } else {
      out[k] = b[k];
    }
  }
  return out;
}

onMounted(build);
onBeforeUnmount(() => network?.destroy());

watch(
  () => [props.nodes, props.edges],
  () => network?.setData({ nodes: props.nodes as any, edges: props.edges as any }),
  { deep: true },
);

defineExpose({
  fit() { network?.fit({ animation: { duration: 600, easingFunction: 'easeInOutCubic' } } as any); },
  focus(id: string | number) { network?.focus(id, { scale: 1.2, animation: true }); },
  network: () => network,
  setNodeOpacity(opaqueIds: Set<string | number>, dimAlpha = 0.15) {
    if (!network) return;
    const updates: any[] = [];
    for (const n of props.nodes as any[]) {
      const isOn = opaqueIds.has(n.id);
      updates.push({ id: n.id, opacity: isOn ? 1 : dimAlpha });
    }
    (network as any).body.data.nodes.update(updates);
  },
  resetNodeOpacity() {
    if (!network) return;
    const updates: any[] = [];
    for (const n of props.nodes as any[]) updates.push({ id: n.id, opacity: 1 });
    (network as any).body.data.nodes.update(updates);
  },
});
</script>

<style scoped>
.network-canvas {
  width: 100%;
  height: 100%;
  background: var(--bg-base, #0a0e17);
}
</style>
