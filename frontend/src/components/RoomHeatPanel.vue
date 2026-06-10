<!--
  Real-time room occupancy heatmap.
  Pulls NPC positions from the live world snapshot and renders one horizontal
  heat bar per room, sorted by current head-count.
-->
<template>
  <div class="rhp">
    <div class="rhp-head">
      <h3 class="rhp-title">
        {{ lang.t('🔥 房间人流热力', '🔥 Room Heatmap') }}
      </h3>
      <span class="rhp-meta">
        {{ lang.t('总 NPC', 'total NPCs') }}
        <b>{{ totalNpcs }}</b>
        · {{ lang.t('占用房间', 'rooms in use') }}
        <b>{{ activeRooms }}</b>
      </span>
    </div>

    <div v-if="!sortedRooms.length" class="rhp-empty">
      {{ lang.t('暂无数据（世界尚未加载）', 'no data yet (world not loaded)') }}
    </div>

    <div class="rhp-rows">
      <div
        v-for="r in sortedRooms"
        :key="r.uid"
        class="rhp-row"
        :class="{ active: r.uid === highlightUid }"
        :title="`${r.name} · ${r.uid}\n${r.count} ${lang.t('人', 'NPCs')}`"
        @click="$emit('select-room', r.uid)"
      >
        <span class="rhp-name">{{ r.name }}</span>
        <span class="rhp-bar-wrap">
          <span
            class="rhp-bar"
            :style="{
              width: r.barW + '%',
              background: `linear-gradient(90deg, ${heatColor(r.t * 0.4)}, ${heatColor(r.t)})`,
            }"
          ></span>
        </span>
        <span class="rhp-num">{{ r.count }}</span>
      </div>
    </div>

    <div class="rhp-ramp">
      <span class="rhp-ramp-label">{{ lang.t('冷清', 'quiet') }}</span>
      <span class="rhp-ramp-bar"></span>
      <span class="rhp-ramp-label">{{ lang.t('拥挤', 'busy') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';

const lang = useLangStore();
defineEmits<{ (e: 'select-room', uid: string): void }>();

interface Room { uid: string; name: string }
interface Props {
  rooms: Room[];
  /** Map of agentId -> { location_uid }. Accepts any object with that field. */
  worldAgents: Record<string, any> | null;
  /** UID currently selected in the graph (for visual highlight). */
  highlightUid?: string | null;
  /** When non-empty, only count these agents (e.g. the user's tracked set). */
  filterAgentIds?: string[];
}
const props = defineProps<Props>();

const countsByRoom = computed<Record<string, number>>(() => {
  const out: Record<string, number> = {};
  const wa = props.worldAgents || {};
  const allow = props.filterAgentIds && props.filterAgentIds.length
    ? new Set(props.filterAgentIds)
    : null;
  for (const [aid, st] of Object.entries(wa)) {
    if (allow && !allow.has(aid)) continue;
    const uid = (st as any)?.location_uid;
    if (!uid) continue;
    out[uid] = (out[uid] || 0) + 1;
  }
  return out;
});

const totalNpcs = computed(() =>
  Object.values(countsByRoom.value).reduce((a, b) => a + b, 0)
);
const activeRooms = computed(() => Object.keys(countsByRoom.value).length);

const sortedRooms = computed(() => {
  const max = Math.max(1, ...Object.values(countsByRoom.value));
  return (props.rooms || [])
    .map(r => {
      const count = countsByRoom.value[r.uid] || 0;
      const t = count / max;
      return {
        uid: r.uid,
        name: r.name,
        count,
        t,
        barW: Math.sqrt(t) * 100,
      };
    })
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
});

/* Re-use the 7-stop ramp from HeatPanel for visual consistency. */
const RAMP: Array<[number, [number, number, number]]> = [
  [0.00, [13, 18, 39]],
  [0.16, [40, 11, 84]],
  [0.33, [101, 21, 110]],
  [0.50, [165, 44, 96]],
  [0.66, [222, 73, 65]],
  [0.83, [248, 142, 35]],
  [1.00, [252, 230, 110]],
];
function heatColor(t: number): string {
  if (t <= 0) return '#0a0e17';
  if (t >= 1) return `rgb(${RAMP[RAMP.length - 1][1].join(',')})`;
  for (let i = 1; i < RAMP.length; i++) {
    const [tHi, cHi] = RAMP[i];
    if (t <= tHi) {
      const [tLo, cLo] = RAMP[i - 1];
      const k = (t - tLo) / (tHi - tLo);
      const r = Math.round(cLo[0] + (cHi[0] - cLo[0]) * k);
      const g = Math.round(cLo[1] + (cHi[1] - cLo[1]) * k);
      const b = Math.round(cLo[2] + (cHi[2] - cLo[2]) * k);
      return `rgb(${r},${g},${b})`;
    }
  }
  return '#0a0e17';
}
</script>

<style scoped>
.rhp { padding: 10px 14px; }
.rhp-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 8px;
}
.rhp-title { color: var(--accent-warn); font-size: 13px; font-weight: 600; }
.rhp-meta { color: var(--text-very-dim); font-size: 11px; }
.rhp-meta b { color: var(--accent-warm-soft); margin: 0 4px; }
.rhp-empty {
  color: var(--text-disabled); font-size: 12px; padding: 12px 4px; text-align: center;
}
.rhp-rows {
  max-height: 38vh;
  overflow-y: auto;
  padding-right: 4px;
}
.rhp-row {
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  margin-bottom: 4px;
  padding: 2px 4px;
  border-radius: 0;
  cursor: pointer;
}
.rhp-row:hover { background: rgba(255,255,255,0.04); }
.rhp-row.active { background: rgba(66, 165, 245, 0.12); outline: 1px solid var(--accent-primary); }
.rhp-name {
  width: 96px;
  color: var(--text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  flex-shrink: 0;
}
.rhp-bar-wrap {
  flex: 1;
  height: 14px;
  background: var(--bg-card);
  border-radius: 0;
  box-shadow: inset 0 0 0 1px var(--bg-elevated);
  overflow: hidden;
}
.rhp-bar {
  display: block;
  height: 100%;
  min-width: 1px;
  border-radius: 0;
  transition: width .3s ease;
}
.rhp-num {
  width: 26px;
  text-align: right;
  font-family: var(--font-mono);
  color: var(--accent-warm-soft);
  font-size: 11px;
}
.rhp-ramp {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--text-very-dim);
}
.rhp-ramp-bar {
  flex: 1;
  height: 8px;
  border-radius: 0;
  background: linear-gradient(
    90deg,
    rgb(13,18,39), rgb(40,11,84), rgb(101,21,110),
    rgb(165,44,96), rgb(222,73,65), rgb(248,142,35), rgb(252,230,110)
  );
  box-shadow: inset 0 0 0 1px var(--bg-elevated);
}
</style>
