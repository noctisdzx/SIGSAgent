<!--
  Global timeline page.
  LEFT  : live WS event stream (TimelineFeed component).
  RIGHT : seeded narrative timeline events grouped by day.
-->
<template>
  <div class="tl">
    <section class="tl-left">
      <TimelineFeed />
    </section>
    <section class="tl-right">
      <div class="header">
        <h2>{{ lang.t('一周高亮事件', 'Weekly Highlights') }}</h2>
        <div class="meta">
          {{ lang.t('共', 'Total') }}
          <b>{{ store.seedEvents.length }}</b>
          {{ lang.t('条', 'events') }}
        </div>
      </div>
      <div class="filter-row">
        <span class="row-label">{{ lang.t('按日期', 'By day') }}</span>
        <span
          class="filter-chip"
          :class="{ active: dayFilter === 'all' }"
          @click="dayFilter = 'all'"
        >
          {{ lang.t('全部', 'All') }}
        </span>
        <span
          v-for="d in availableDays"
          :key="d"
          class="filter-chip"
          :class="{ active: dayFilter === d }"
          @click="dayFilter = d"
        >
          {{ d }}
        </span>
      </div>
      <div class="rows">
        <div v-if="!filtered.length" class="placeholder">
          {{ lang.t('无种子时间线事件。', 'No seeded timeline events.') }}
        </div>
        <template v-for="d in groupedDays" :key="d.day">
          <div class="day">{{ d.day }}</div>
          <div v-for="(ev, i) in d.events" :key="i" class="event">
            <span class="time">{{ ev.time || (ev.ts || '').slice(11, 16) }}</span>
            <span class="title">{{ titleOf(ev) }}</span>
            <span v-if="ev.location_uid" class="loc">@{{ ev.location_uid }}</span>
            <div class="narr">{{ narrativeOf(ev) }}</div>
            <div v-if="ev.people?.length" class="people">
              <span v-for="p in ev.people" :key="p" class="person">· {{ p }}</span>
            </div>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import TimelineFeed from '@/components/TimelineFeed.vue';
import { useLangStore } from '@/stores/lang';
import { useTimelineStore } from '@/stores/timeline';
import type { TimelineEvent } from '@/api/endpoints';

const lang = useLangStore();
const store = useTimelineStore();
const dayFilter = ref<string>('all');

const availableDays = computed<string[]>(() => {
  const set = new Set<string>();
  for (const ev of store.seedEvents) {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '');
    if (d) set.add(d);
  }
  return Array.from(set).sort();
});
const filtered = computed<TimelineEvent[]>(() => {
  if (dayFilter.value === 'all') return store.seedEvents;
  return store.seedEvents.filter(ev => {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '');
    return d === dayFilter.value;
  });
});
const groupedDays = computed(() => {
  const map: Record<string, TimelineEvent[]> = {};
  for (const ev of filtered.value) {
    const d = ev.day || (ev.ts ? ev.ts.slice(0, 10) : '—');
    (map[d] = map[d] || []).push(ev);
  }
  return Object.entries(map).map(([day, events]) => ({ day, events }));
});

function titleOf(ev: TimelineEvent): string {
  return lang.lang === 'en' ? (ev.title_en || ev.title || '') : (ev.title || ev.title_en || '');
}
function narrativeOf(ev: TimelineEvent): string {
  return lang.lang === 'en' ? (ev.narrative_en || ev.narrative_zh || '') : (ev.narrative_zh || ev.narrative_en || '');
}

onMounted(() => store.loadSeed());
</script>

<style scoped>
.tl { display: flex; height: 100%; }
.tl-left {
  flex: 1;
  border-right: 1px solid var(--border-soft);
  padding: 14px 18px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
  min-width: 0;
}
.tl-right {
  flex: 1;
  background: var(--bg-panel);
  padding: 14px 18px;
  overflow-y: auto;
  min-width: 0;
}
.header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-soft);
  padding-bottom: 8px;
}
.header h2 { color: var(--accent-warn); font-size: 16px; }
.meta { color: var(--text-very-dim); font-size: 11.5px; }
.meta b { color: var(--accent-warn); }

.filter-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  margin-bottom: 12px;
}
.row-label { font-size: 11px; color: var(--text-very-dim); margin-right: 6px; }

.day {
  color: var(--accent-primary);
  font-weight: 600;
  font-size: 13px;
  border-bottom: 1px dashed var(--border-soft);
  margin: 12px 0 4px;
  padding-bottom: 2px;
}
.event {
  background: var(--bg-card);
  padding: 6px 10px;
  border-left: 2px solid var(--accent-warn);
  border-radius: 4px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.event .time {
  color: var(--accent-warn);
  font-weight: 600;
  min-width: 46px;
  display: inline-block;
  font-family: Consolas, monospace;
  margin-right: 6px;
}
.event .title { color: var(--accent-primary); }
.event .loc { color: var(--text-very-dim); font-size: 10px; margin-left: 6px; }
.event .narr { color: var(--text-secondary); font-size: 11.5px; line-height: 1.55; margin-top: 2px; }
.event .people { color: var(--accent-good-soft); font-size: 10.5px; margin-top: 2px; }
.placeholder { color: var(--text-disabled); font-size: 12px; padding: 18px 0; }
</style>
