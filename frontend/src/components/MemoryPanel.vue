<!-- STM / LTM 双列表 + hit_count badge + degraded 标记 -->
<template>
  <div class="memory-panel">
    <section>
      <h3>短期记忆 (STM) · {{ stm.length }}/30</h3>
      <div v-if="!stm.length" class="empty">（暂无）</div>
      <div v-for="m in stm" :key="m.id" class="mem-item">
        <div class="meta">
          <span>{{ m.ts }}</span>
          <span class="hit">hit ×{{ m.hit_count }}</span>
        </div>
        <div class="text">{{ m.text }}</div>
      </div>
    </section>
    <section>
      <h3>长期记忆 (LTM) · {{ ltm.length }}/15</h3>
      <div v-if="!ltm.length" class="empty">（暂无）</div>
      <div v-for="m in ltm" :key="m.id" class="mem-item">
        <div class="meta">
          <span>{{ m.ts }}</span>
          <span class="hit">hit ×{{ m.hit_count }}</span>
          <span v-if="m.degraded" class="degraded">degraded</span>
        </div>
        <div class="text">{{ m.text }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
defineProps<{ stm: any[]; ltm: any[] }>();
</script>

<style scoped>
.memory-panel { padding: 12px; }
.memory-panel h3 { color: #ffe082; font-size: 13px; margin: 10px 0 6px; }
.mem-item {
  background: #0d1220;
  border-left: 3px solid #42a5f5;
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 4px;
}
.meta { display: flex; gap: 8px; font-size: 10.5px; color: #78909c; margin-bottom: 2px; }
.hit { color: #ffa726; }
.degraded { color: #ef9a9a; }
.text { font-size: 12.5px; color: #cfd8dc; }
.empty { color: #546e7a; font-size: 12px; padding: 4px 0; }
</style>
