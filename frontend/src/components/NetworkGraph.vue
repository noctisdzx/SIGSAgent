<!--
  Generic vis-network wrapper.
  Used by RelationView (NPC graph), SceneGraphView (room graph),
  and MemoryGraphView (triplet graph).
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

const emit = defineEmits<{ (e: 'selectNode', id: string): void }>();

const el = ref<HTMLDivElement | null>(null);
let network: Network | null = null;

const DEFAULT_OPTS: Options = {
  nodes: {
    shape: 'dot',
    size: 18,
    color: { background: '#1a2240', border: '#42a5f5', highlight: '#90caf9' },
    font: { color: '#e0e0e0', size: 13 },
    borderWidth: 1.5,
  },
  edges: {
    color: { color: '#1e2a45', highlight: '#42a5f5' },
    smooth: { enabled: true, type: 'dynamic', roundness: 0.4 },
  },
  physics: {
    barnesHut: { gravitationalConstant: -2000, springLength: 120 },
  },
  interaction: { hover: true, tooltipDelay: 200 },
};

function build() {
  if (!el.value) return;
  const data: Data = { nodes: props.nodes as any, edges: props.edges as any };
  network = new Network(el.value, data, { ...DEFAULT_OPTS, ...(props.options || {}) });
  network.on('selectNode', (params: any) => {
    if (params.nodes?.length) emit('selectNode', String(params.nodes[0]));
  });
}

onMounted(build);
onBeforeUnmount(() => network?.destroy());
watch(() => [props.nodes, props.edges], () => {
  network?.setData({ nodes: props.nodes as any, edges: props.edges as any });
}, { deep: true });
</script>

<style scoped>
.network-canvas {
  width: 100%;
  height: 100%;
  background: #0a0e17;
}
</style>
