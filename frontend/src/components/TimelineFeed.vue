<!--
  Live WS event feed.
  Renders a rolling list of events from `useEventsStore().stream`.
  Color-codes by event type:
    tick            → blue
    agent_decision  → orange
    behavior        → green
    memory_update   → purple
    agent_error     → red
-->
<template>
  <div class="feed">
    <div class="feed-header">
      <span class="title">{{ lang.t('实时事件流', 'Live Event Stream') }}</span>
      <span class="meta">
        {{ lang.t('已收到', 'received') }}
        <b>{{ events.stream.length }}</b>
        {{ lang.t('条', '') }}
      </span>
    </div>
    <div v-if="!events.stream.length" class="empty">
      {{ lang.t(
        '尚未收到事件。确认后端正在运行：POST /api/sim/start。',
        'No events yet. Make sure the backend is running and POST /api/sim/start.'
      ) }}
    </div>
    <div class="rows">
      <div
        v-for="(ev, i) in reversed"
        :key="i"
        class="ev"
        :class="`ev--${ev.type}`"
      >
        <span class="ts">{{ ev.ts_sim || '—' }}</span>
        <span class="type">{{ ev.type }}</span>
        <span v-if="ev.agent_id" class="aid">{{ ev.agent_id }}</span>
        <code class="payload">{{ summary(ev) }}</code>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';

const lang = useLangStore();
const events = useEventsStore();

const reversed = computed(() => events.stream.slice().reverse());

function summary(ev: any): string {
  if (!ev?.payload) return '';
  try {
    const s = JSON.stringify(ev.payload);
    return s.length > 220 ? s.slice(0, 220) + '…' : s;
  } catch { return ''; }
}
</script>

<style scoped>
.feed { display: flex; flex-direction: column; height: 100%; }
.feed-header {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 6px 4px;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: 6px;
}
.title { color: var(--accent-warn); font-weight: 600; font-size: 13px; }
.meta { color: var(--text-very-dim); font-size: 11px; }
.empty {
  color: var(--text-disabled);
  font-size: 12px;
  padding: 16px 4px;
  font-style: italic;
}
.rows { flex: 1; overflow-y: auto; padding-right: 4px; }
.ev {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 11px;
  padding: 5px 8px;
  margin-bottom: 3px;
  background: var(--bg-card);
  border-left: 2px solid var(--border-soft);
  border-radius: 4px;
}
.ev--tick           { border-left-color: var(--accent-active); }
.ev--agent_decision { border-left-color: var(--accent-warn); }
.ev--behavior       { border-left-color: var(--accent-good-soft); }
.ev--memory_update  { border-left-color: var(--accent-purple-soft); }
.ev--agent_error    { border-left-color: var(--accent-danger); }
.ev--welcome        { border-left-color: var(--accent-cyan-soft); }

.ts   { color: var(--accent-warn); min-width: 130px; font-family: Consolas, monospace; }
.type { color: var(--accent-primary); min-width: 110px; }
.aid  { color: var(--accent-good-soft); min-width: 80px; }
.payload {
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  font-family: Consolas, monospace;
  font-size: 10.5px;
}
</style>
