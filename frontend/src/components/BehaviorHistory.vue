<!-- GOAP 解析后的行为执行历史 -->
<template>
  <div class="bh">
    <h3>行为历史</h3>
    <div v-if="!items.length" class="empty">（暂无）</div>
    <div v-for="(it, i) in items" :key="i" class="row" :class="{ fail: it.ok === false }">
      <span class="ts">{{ it.ts }}</span>
      <span class="act">{{ it.action_id }}</span>
      <span class="params">{{ JSON.stringify(it.params || {}) }}</span>
      <span v-if="it.note" class="note">— {{ it.note }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ items: any[] }>();
</script>

<style scoped>
.bh { padding: 12px; }
.bh h3 { color: #ffe082; font-size: 13px; margin: 10px 0 6px; }
.row {
  display: flex;
  gap: 10px;
  font-size: 11.5px;
  padding: 5px 8px;
  margin-bottom: 3px;
  background: #0d1220;
  border-left: 2px solid #42a5f5;
  border-radius: 4px;
}
.row.fail { border-left-color: #ef5350; }
.ts { color: #ffa726; min-width: 90px; }
.act { color: #90caf9; }
.params { color: #a5d6a7; }
.note { color: #78909c; font-style: italic; }
.empty { color: #546e7a; font-size: 12px; }
</style>
