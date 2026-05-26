<!-- 当前可见节点：children + siblings 两栏 -->
<template>
  <div class="pp">
    <h3>感知 · 当前可见</h3>
    <div class="cur">所在：<b>{{ here }}</b></div>
    <div class="cols">
      <div>
        <div class="label">子节点 (children)</div>
        <div v-for="r in children" :key="r.uid" class="room">
          <div class="name">{{ r.name }} <span class="uid">{{ r.uid }}</span></div>
          <div class="meta">agents: {{ r.agents.join(', ') || '—' }}</div>
          <div class="meta">items: {{ r.items.join(', ') || '—' }}</div>
        </div>
      </div>
      <div>
        <div class="label">兄弟节点 (siblings)</div>
        <div v-for="r in siblings" :key="r.uid" class="room">
          <div class="name">{{ r.name }} <span class="uid">{{ r.uid }}</span></div>
          <div class="meta">agents: {{ r.agents.join(', ') || '—' }}</div>
          <div class="meta">items: {{ r.items.join(', ') || '—' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ here: string; children: any[]; siblings: any[] }>();
</script>

<style scoped>
.pp { padding: 12px; }
.pp h3 { color: #ffe082; font-size: 13px; margin: 10px 0 6px; }
.cur { font-size: 12px; color: #cfd8dc; margin-bottom: 8px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.label { color: #90caf9; font-size: 12px; margin-bottom: 6px; }
.room { background: #0d1220; border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; }
.name { font-size: 12.5px; color: #ffe082; }
.uid { color: #78909c; font-size: 10px; margin-left: 4px; }
.meta { font-size: 10.5px; color: #90a4ae; }
</style>
