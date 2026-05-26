<!-- 5min 槽位时间轴。模板项与片段填充用不同色块。 -->
<template>
  <div class="schedule-panel">
    <h3>当日日程 · 5min 槽位</h3>
    <div class="timeline">
      <div
        v-for="s in slots"
        :key="s.index"
        class="slot"
        :class="s.kind"
        :title="`${s.start} ~ ${s.end}  ${s.activity || ''}`"
      >
        <span class="t">{{ s.start.slice(11, 16) }}</span>
        <span class="a">{{ s.activity || '·' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ slots: any[] }>();
</script>

<style scoped>
.schedule-panel { padding: 12px; }
.schedule-panel h3 { color: #ffe082; font-size: 13px; margin: 10px 0 8px; }
.timeline { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; }
.slot {
  display: flex;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11.5px;
  background: #0d1220;
  border-left: 3px solid #1e2a45;
}
.slot.template { border-left-color: #ffa726; }
.slot.fragment { border-left-color: #26c6da; }
.slot.empty    { opacity: .4; }
.t { color: #ffa726; min-width: 38px; }
.a { color: #cfd8dc; }
</style>
