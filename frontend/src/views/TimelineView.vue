<!--
  全局时间线：基于 WS 流的 tick / agent_decision / behavior 事件。
-->
<template>
  <div class="tl-page">
    <h2>全局时间线</h2>
    <div v-if="!events.stream.length" class="empty">尚未收到事件（确认后端已 /sim/start）</div>
    <div v-for="(ev, i) in events.stream.slice().reverse()" :key="i" class="ev" :class="ev.type">
      <span class="ts">{{ ev.ts_sim }}</span>
      <span class="type">{{ ev.type }}</span>
      <span v-if="ev.agent_id" class="aid">{{ ev.agent_id }}</span>
      <code>{{ JSON.stringify(ev.payload) }}</code>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useEventsStore } from '@/stores/events';
const events = useEventsStore();
</script>

<style scoped>
.tl-page { padding: 18px 24px; overflow-y: auto; height: 100%; }
h2 { color: #ffa726; font-size: 16px; margin-bottom: 12px; }
.empty { color: #546e7a; font-size: 12px; }
.ev {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
  padding: 6px 10px;
  margin-bottom: 4px;
  background: #0d1220;
  border-left: 2px solid #1e2a45;
  border-radius: 4px;
}
.ev.tick { border-left-color: #42a5f5; }
.ev.agent_decision { border-left-color: #ffa726; }
.ev.agent_error { border-left-color: #ef5350; }
.ts { color: #ffa726; min-width: 150px; }
.type { color: #90caf9; min-width: 110px; }
.aid { color: #a5d6a7; min-width: 100px; }
code { color: #cfd8dc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
</style>
