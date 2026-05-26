<!--
  场景拓扑图视图：基于 guoyi_rooms_v2.json 的 adjacent 字段。
  上线后会通过 /api/scene/graph 拉取数据。
-->
<template>
  <div class="scene-page">
    <NetworkGraph :nodes="nodes" :edges="edges" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
import { useWorldStore } from '@/stores/world';

const nodes = ref<any[]>([]);
const edges = ref<any[]>([]);

const world = useWorldStore();

onMounted(async () => {
  try {
    await world.loadScene();
    const rooms = world.sceneGraph?.rooms || [];
    nodes.value = rooms.map(r => ({
      id: r.uid,
      label: r.name,
      title: r.description,
      group: r.tag?.[0] || 'misc',
    }));
    const seen = new Set<string>();
    const e: any[] = [];
    rooms.forEach(r => {
      (r.adjacent || []).forEach(a => {
        const k = [r.uid, a].sort().join('|');
        if (seen.has(k)) return;
        seen.add(k);
        e.push({ from: r.uid, to: a });
      });
    });
    edges.value = e;
  } catch (err) {
    console.warn('Scene graph not available yet', err);
  }
});
</script>

<style scoped>
.scene-page { height: 100%; }
</style>
