<!--
  GOAP behavior execution history.
  Items shape: { ts, action_id, params, ok, note }
-->
<template>
  <div class="bh">
    <h3>{{ lang.t('行为历史', 'Behavior History') }}</h3>
    <div v-if="!items.length" class="empty">{{ lang.t('（暂无）', '(empty)') }}</div>
    <div v-for="(it, i) in items" :key="i" class="row" :class="{ fail: it.ok === false }">
      <span class="ts">{{ it.ts }}</span>
      <span class="act">{{ it.action_id }}</span>
      <span class="params">{{ paramText(it.params) }}</span>
      <span v-if="it.note" class="note">— {{ it.note }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLangStore } from '@/stores/lang';
const lang = useLangStore();

defineProps<{ items: any[] }>();

function paramText(p: any): string {
  if (!p) return '';
  try { return JSON.stringify(p); } catch { return String(p); }
}
</script>

<style scoped>
.bh { padding: 12px; }
.bh h3 { color: var(--accent-warm-soft); font-size: 13px; margin: 4px 0 8px; }
.row {
  display: flex;
  gap: 10px;
  font-size: 11.5px;
  padding: 5px 8px;
  margin-bottom: 3px;
  background: var(--bg-card);
  border-left: 2px solid var(--accent-active);
  border-radius: 4px;
}
.row.fail { border-left-color: var(--accent-danger); }
.ts     { color: var(--accent-warn); min-width: 130px; font-family: Consolas, monospace; }
.act    { color: var(--accent-primary); min-width: 80px; }
.params { color: var(--accent-good-soft); flex: 1; font-family: Consolas, monospace; font-size: 10.5px; }
.note   { color: var(--text-very-dim); font-style: italic; }
.empty  { color: var(--text-disabled); font-size: 12px; }
</style>
