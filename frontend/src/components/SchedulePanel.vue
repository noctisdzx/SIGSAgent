<!--
  5-minute slot timeline (288 slots/day).
  Renders as a 24×12 dense grid (24 hours, 12 slots per hour).
  Hover for the full activity tooltip.
-->
<template>
  <div class="sched">
    <div class="sched-header">
      <h3>{{ lang.t('当日日程 · 5min 槽位', 'Today\'s Schedule · 5-min slots') }}</h3>
      <div class="legend">
        <span class="lg lg--template" /> {{ lang.t('模板项', 'Template') }}
        <span class="lg lg--fragment" /> {{ lang.t('片段填充', 'Fragment') }}
        <span class="lg lg--empty" />    {{ lang.t('空闲', 'Empty') }}
      </div>
    </div>
    <div v-if="!slots.length" class="empty">{{ lang.t('（暂无）', '(empty)') }}</div>
    <div v-else class="grid">
      <div
        v-for="s in slots"
        :key="s.index"
        class="slot"
        :class="`slot--${s.kind || 'empty'}`"
        :title="`${formatHM(s.start)} ~ ${formatHM(s.end)}  ${s.activity || ''}`"
      >
        <span v-if="s.index % 12 === 0" class="hour">{{ formatHM(s.start) }}</span>
      </div>
    </div>

    <div class="active-list">
      <div v-for="s in active" :key="s.index" class="row" :class="`row--${s.kind || 'empty'}`">
        <span class="t">{{ formatHM(s.start) }}–{{ formatHM(s.end) }}</span>
        <span class="a">{{ s.activity || '·' }}</span>
        <span v-if="s.location_uid" class="loc">@{{ s.location_uid }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';
const lang = useLangStore();

const props = defineProps<{ slots: any[] }>();

function formatHM(ts: string): string {
  if (!ts) return '';
  // "2026-05-26T10:00:00" → "10:00"
  return ts.includes('T') ? ts.slice(11, 16) : ts.slice(0, 5);
}
const active = computed(() => (props.slots || []).filter(s => s && s.kind && s.kind !== 'empty'));
</script>

<style scoped>
.sched { padding: 12px; }
.sched-header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 8px;
}
.sched h3 { color: var(--accent-warm-soft); font-size: 13px; }
.legend { display: flex; gap: 8px; font-size: 10.5px; color: var(--text-very-dim); align-items: center; }
.lg { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.lg--template { background: var(--accent-warn); }
.lg--fragment { background: var(--accent-cyan-soft); }
.lg--empty    { background: var(--bg-elevated); }

.grid {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  gap: 1px;
  background: var(--bg-card);
  padding: 6px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.slot {
  height: 8px;
  background: var(--bg-elevated);
  border-radius: 1px;
  position: relative;
}
.slot--template { background: var(--accent-warn); }
.slot--fragment { background: var(--accent-cyan-soft); }
.slot .hour {
  position: absolute;
  top: -16px; left: 0;
  font-size: 9px;
  color: var(--text-very-dim);
  font-family: Consolas, monospace;
}

.active-list {
  background: var(--bg-card);
  border-radius: 6px;
  padding: 8px;
  font-size: 11.5px;
}
.row {
  display: flex; gap: 10px;
  padding: 3px 6px;
  border-left: 2px solid var(--border-soft);
  margin-bottom: 2px;
  border-radius: 3px;
  background: rgba(255,255,255,0.01);
}
.row--template { border-left-color: var(--accent-warn); }
.row--fragment { border-left-color: var(--accent-cyan-soft); }
.t   { color: var(--accent-warn); min-width: 105px; font-family: Consolas, monospace; }
.a   { color: var(--text-secondary); flex: 1; }
.loc { color: var(--text-very-dim); font-size: 10px; }
.empty { color: var(--text-disabled); font-size: 12px; }
</style>
