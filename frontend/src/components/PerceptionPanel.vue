<!--
  Current visible-nodes panel: children + siblings two columns.
-->
<template>
  <div class="pp">
    <h3>{{ lang.t('感知 · 当前可见', 'Perception · Visible') }}</h3>
    <div class="cur">{{ lang.t('所在', 'Here') }}：<b>{{ here || '—' }}</b></div>
    <div class="cols">
      <div>
        <div class="label">{{ lang.t('子节点 (children)', 'Children') }}</div>
        <div v-for="r in children" :key="r.uid" class="room">
          <div class="name">{{ r.name }} <span class="uid">{{ r.uid }}</span></div>
          <div class="meta">{{ lang.t('agents', 'agents') }}: {{ (r.agents || []).join(', ') || '—' }}</div>
          <div class="meta">{{ lang.t('items', 'items') }}: {{ (r.items || []).join(', ') || '—' }}</div>
        </div>
        <div v-if="!children.length" class="empty">{{ lang.t('（无）', '(none)') }}</div>
      </div>
      <div>
        <div class="label">{{ lang.t('兄弟节点 (siblings)', 'Siblings') }}</div>
        <div v-for="r in siblings" :key="r.uid" class="room">
          <div class="name">{{ r.name }} <span class="uid">{{ r.uid }}</span></div>
          <div class="meta">{{ lang.t('agents', 'agents') }}: {{ (r.agents || []).join(', ') || '—' }}</div>
          <div class="meta">{{ lang.t('items', 'items') }}: {{ (r.items || []).join(', ') || '—' }}</div>
        </div>
        <div v-if="!siblings.length" class="empty">{{ lang.t('（无）', '(none)') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLangStore } from '@/stores/lang';
const lang = useLangStore();
defineProps<{ here?: string; children: any[]; siblings: any[] }>();
</script>

<style scoped>
.pp { padding: 12px; }
.pp h3 { color: var(--accent-warm-soft); font-size: 13px; margin: 4px 0 6px; }
.cur { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.label { color: var(--accent-primary); font-size: 12px; margin-bottom: 6px; }
.room { background: var(--bg-card); border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; }
.name { font-size: 12.5px; color: var(--accent-warm-soft); }
.uid { color: var(--text-very-dim); font-size: 10px; margin-left: 4px; font-family: Consolas, monospace; }
.meta { font-size: 10.5px; color: var(--text-dim); }
.empty { color: var(--text-disabled); font-size: 11px; padding: 4px 0; }
</style>
