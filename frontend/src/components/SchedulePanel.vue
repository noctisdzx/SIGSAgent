<!--
  Weekly schedule rendered like a school timetable (课表):
    - columns  = 周一 … 周日
    - vertical = time of day (00:00 → 24:00)
    - activities are color blocks positioned by their start/end time.

  Data is the pre-loaded template (from persontimetable CSVs) plus live fills
  (fragments / insert events). The panel polls every few seconds so empty slots
  fill in as the sim advances; each weekday resets when the sim rolls around to
  it again.
-->
<template>
  <div class="sched">
    <div class="sched-header">
      <h3>{{ lang.t('周课表 · 模板 + 实时填充', 'Weekly Timetable · template + live fill') }}</h3>
      <div class="legend">
        <span class="lg lg--template" /> {{ lang.t('模板', 'Template') }}
        <span class="lg lg--fragment" /> {{ lang.t('片段', 'Fragment') }}
        <span class="lg lg--insert" /> {{ lang.t('插入事件', 'Insert') }}
        <span class="lg lg--empty" /> {{ lang.t('空闲', 'Empty') }}
      </div>
    </div>

    <div v-if="!dayRuns.length" class="empty">{{ lang.t('（加载中…）', '(loading…)') }}</div>

    <div v-else class="tt">
      <!-- column headers -->
      <div class="tt-head">
        <span class="corner" />
        <span
          v-for="d in dayRuns"
          :key="d.weekday"
          class="head-cell"
          :class="{ today: d.is_today }"
        >
          {{ lang.lang === 'en' ? d.label_en : d.label_zh }}
        </span>
      </div>

      <!-- scrollable body -->
      <div class="tt-body" :style="{ height: bodyHeight + 'px' }">
        <!-- time ruler -->
        <div class="time-col">
          <div
            v-for="h in 24"
            :key="h"
            class="time-label"
            :style="{ top: (h - 1) * pxPerHour + 'px' }"
          >{{ String(h - 1).padStart(2, '0') }}:00</div>
        </div>

        <!-- one column per weekday -->
        <div
          v-for="d in dayRuns"
          :key="d.weekday"
          class="day-col"
          :class="{ today: d.is_today }"
        >
          <div
            v-for="h in 24"
            :key="'l' + h"
            class="hour-line"
            :style="{ top: h * pxPerHour + 'px' }"
          />
          <div
            v-if="d.is_today && currentSlotIndex >= 0"
            class="now-line"
            :style="{ top: nowTop + 'px' }"
          />
          <div
            v-for="(r, i) in d.runs"
            :key="i"
            class="blk"
            :class="[`blk--${r.kind}`, { 'blk--compact': blkH(r) < 50, 'blk--tiny': blkH(r) < 16 }]"
            :style="{ top: top(r.from) + 'px', height: Math.max(blkH(r) - 1, 3) + 'px' }"
            :title="`${hm(r.from)}–${hm(r.to)}  ${r.activity}${r.location_uid ? ' @' + r.location_uid : ''}`"
          >
            <span v-if="blkH(r) >= 50" class="blk-time">{{ hm(r.from) }}</span>
            <span class="blk-act">{{ r.activity }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { api } from '@/api/endpoints';
import { useLangStore } from '@/stores/lang';

const lang = useLangStore();
const props = defineProps<{ agentId: string | null }>();

const POLL_MS = 4000;
const SLOT_MIN = 5;
const pxPerHour = 54;
const bodyHeight = pxPerHour * 24;

const days = ref<any[]>([]);
const currentSlotIndex = ref<number>(-1);
let timer: number | null = null;

function hm(index: number): string {
  const m = index * SLOT_MIN;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}
function top(fromIdx: number): number {
  return (fromIdx * SLOT_MIN) / 60 * pxPerHour;
}
function height(fromIdx: number, toIdx: number): number {
  return ((toIdx - fromIdx) * SLOT_MIN) / 60 * pxPerHour;
}
function blkH(r: { from: number; to: number }): number {
  return height(r.from, r.to);
}
const nowTop = computed(() => (currentSlotIndex.value * SLOT_MIN) / 60 * pxPerHour);

function cellKind(s: any): string {
  if (typeof s.source_id === 'string' && s.source_id.startsWith('insert:')) return 'insert';
  return s.kind || 'empty';
}

// Merge contiguous non-empty slots sharing (kind, activity, location, source).
function mergeRuns(slots: any[]): any[] {
  const out: any[] = [];
  let i = 0;
  while (i < slots.length) {
    const s = slots[i];
    if (!s.activity || s.kind === 'empty') { i++; continue; }
    const key = (x: any) => `${cellKind(x)}|${x.activity}|${x.location_uid}|${x.source_id}`;
    const k0 = key(s);
    let j = i;
    while (j + 1 < slots.length && slots[j + 1].activity && key(slots[j + 1]) === k0) j++;
    out.push({
      from: s.index,
      to: slots[j].index + 1,
      kind: cellKind(s),
      activity: s.activity,
      location_uid: s.location_uid,
    });
    i = j + 1;
  }
  return out;
}

const dayRuns = computed(() =>
  days.value.map(d => ({ ...d, runs: mergeRuns(d.slots || []) })),
);

async function fetchWeek() {
  const id = props.agentId;
  if (!id) return;
  try {
    const data = await api.agentSchedule(id, undefined, true);
    if (data && data.mode === 'week') {
      days.value = data.days || [];
      currentSlotIndex.value = data.current_slot_index ?? -1;
    }
  } catch (err) {
    console.warn('[schedule] week fetch failed', err);
  }
}

function startPolling() {
  stopPolling();
  fetchWeek();
  timer = window.setInterval(fetchWeek, POLL_MS);
}
function stopPolling() {
  if (timer !== null) { window.clearInterval(timer); timer = null; }
}

watch(() => props.agentId, () => { days.value = []; startPolling(); }, { immediate: true });
onBeforeUnmount(stopPolling);
</script>

<style scoped>
.sched { padding: 12px; }
.sched-header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 10px; flex-wrap: wrap; gap: 6px;
}
.sched h3 { color: var(--accent-warm-soft); font-size: 13px; }
.legend { display: flex; gap: 8px; font-size: 10.5px; color: var(--text-very-dim); align-items: center; }
.lg { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.lg--template { background: var(--accent-warn); }
.lg--fragment { background: var(--accent-cyan-soft); }
.lg--insert   { background: var(--accent-primary); }
.lg--empty    { background: var(--bg-elevated); }

.tt {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-card);
}

/* header row */
.tt-head {
  display: grid;
  grid-template-columns: 46px repeat(7, 1fr);
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.corner { }
.head-cell {
  text-align: center;
  font-size: 11.5px;
  padding: 6px 0;
  color: var(--text-muted);
  border-left: 1px solid var(--border-soft);
}
.head-cell.today { color: var(--accent-primary); font-weight: 700; background: var(--bg-elevated-hover); }

/* body: time ruler + 7 day columns */
.tt-body {
  display: grid;
  grid-template-columns: 46px repeat(7, 1fr);
  overflow-y: auto;
  position: relative;
}
.time-col { position: relative; }
.time-label {
  position: absolute; right: 6px;
  transform: translateY(-50%);
  font-size: 9.5px; color: var(--text-very-dim);
  font-family: Consolas, monospace;
}

.day-col {
  position: relative;
  border-left: 1px solid var(--border-soft);
}
.day-col.today { background: rgba(255,255,255,0.02); }
.hour-line {
  position: absolute; left: 0; right: 0; height: 0;
  border-top: 1px dashed var(--border-soft);
  opacity: 0.4;
}
.now-line {
  position: absolute; left: 0; right: 0; height: 0;
  border-top: 1.5px solid var(--accent-primary);
  z-index: 5;
}
.now-line::before {
  content: ''; position: absolute; left: 0; top: -3px;
  width: 5px; height: 5px; border-radius: 50%; background: var(--accent-primary);
}

.blk {
  position: absolute; left: 2px; right: 2px;
  border-radius: 3px;
  padding: 1px 4px;
  overflow: hidden;
  font-size: 9.5px;
  line-height: 1.18;
  color: var(--bg-base);
  cursor: default;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}
.blk-time { display: block; font-family: Consolas, monospace; opacity: 0.85; font-size: 8.5px; flex: 0 0 auto; }
.blk-act  {
  display: block;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  overflow: hidden;
  font-weight: 600; flex: 1 1 auto; min-height: 0;
}
/* Short blocks: no separate time line — the activity uses the whole cell,
   wrapped and centered, so it never spills past the bottom edge. */
.blk--compact { justify-content: center; padding: 0 4px; }
.blk--compact .blk-act { font-size: 9px; line-height: 1.05; text-align: center; }
/* Very short blocks (≤15 min): one line with ellipsis (no room to wrap). */
.blk--tiny { padding: 0 3px; }
.blk--tiny .blk-act {
  font-size: 8px; line-height: 1;
  white-space: nowrap; text-overflow: ellipsis;
}
.blk--template { background: var(--accent-warn); }
.blk--fragment { background: var(--accent-cyan-soft); }
.blk--insert   { background: var(--accent-primary); color: #fff; }

.empty { color: var(--text-disabled); font-size: 12px; padding: 8px; }
</style>
