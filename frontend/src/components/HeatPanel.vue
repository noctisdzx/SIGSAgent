<!--
  Heat panel — relation intensity matrix.
  See §12 of `docs/reference_ux_spec.md`.

  This is a lightweight implementation: we use the *relation* edges as the
  "temperature" signal, since relation weight maps cleanly to the 7-stop ramp
  defined in the spec. We render two views:
    1. Top relation pairs (sorted by weight) as a horizontal bar chart.
    2. NPC × NPC heat matrix (square cells colored by relation weight).
-->
<template>
  <div class="heat">
    <h3 class="hh">{{ lang.t('🌡️ 关系热度排行', '🌡️ Relation Heat Ranking') }}</h3>
    <div class="hint">
      {{ lang.t(
        '一周内每对 NPC 之间的关系强度（按 √ 缩放，最热 = 黄色）。',
        'Relation intensity between NPC pairs (sqrt-scaled, hottest = yellow).'
      ) }}
    </div>

    <div class="bars">
      <div v-for="r in topRows" :key="`${r.from}|${r.to}`" class="hm-row">
        <span class="hm-space">{{ r.fromName }} ⇌ {{ r.toName }}</span>
        <span class="hm-bar-wrap">
          <span class="hm-bar"
                :style="{
                  width: r.barW + '%',
                  background: `linear-gradient(90deg, ${heatColor(r.t * 0.4)}, ${heatColor(r.t)})`,
                }">
            <span v-if="r.t > 0.45" class="hm-bar-label">{{ r.weight.toFixed(2) }}</span>
          </span>
        </span>
        <span class="hm-num">{{ r.weight.toFixed(2) }}</span>
      </div>
    </div>

    <h3 class="hh" style="margin-top:14px;">
      {{ lang.t('🔥 关系热度矩阵', '🔥 Relation Heat Matrix') }}
    </h3>
    <div class="hint">
      {{ lang.t(
        '横纵轴均为 NPC（按分组聚类）。颜色越亮表示关系强度越高。',
        'Both axes are NPCs (clustered by group). Brighter = stronger.'
      ) }}
    </div>

    <div class="hm-grid-wrap">
      <div class="hm-grid">
        <div class="hm-grid-row hm-axis">
          <div class="hm-grid-label" />
          <div v-for="b in axisIds" :key="`x${b}`" class="hm-axis-cell">{{ shortName(b) }}</div>
        </div>
        <div v-for="a in axisIds" :key="`r${a}`" class="hm-grid-row">
          <div class="hm-grid-label">{{ shortName(a) }}</div>
          <div v-for="b in axisIds" :key="`c${a}|${b}`"
               class="hm-grid-cell"
               :title="`${nameOf(a)} ⇌ ${nameOf(b)} · ${cellWeight(a, b).toFixed(2)}`"
               :style="{ background: heatColor(Math.sqrt(cellWeight(a, b))) }">
          </div>
        </div>
      </div>
    </div>

    <div class="cb-wrap">
      <span class="cb-label">{{ lang.t('冷', 'low') }}</span>
      <span class="cb-bar"></span>
      <span class="cb-label">{{ lang.t('热', 'high') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';
import type { RelationEdge } from '@/api/endpoints';
import { edgeFromTo } from '@/stores/relations';

const lang = useLangStore();
const props = defineProps<{
  edges: RelationEdge[];
  npcMap: Record<string, any>;
}>();

interface Row { from: string; to: string; fromName: string; toName: string; weight: number; t: number; barW: number; }

function nameOf(id: string): string {
  const n = props.npcMap[id];
  if (!n) return id;
  return lang.lang === 'en' ? (n.name_en || n.name || id) : (n.name || n.name_en || id);
}
function shortName(id: string): string {
  const full = nameOf(id);
  return full.length > 4 ? full.slice(0, 4) : full;
}

const sortedRows = computed<Row[]>(() => {
  const rows: Row[] = [];
  let max = 0.0001;
  for (const e of props.edges) {
    const { from, to } = edgeFromTo(e);
    if (!from || !to) continue;
    const w = Number(e.weight ?? 0.5);
    rows.push({
      from, to,
      fromName: nameOf(from), toName: nameOf(to),
      weight: w, t: 0, barW: 0,
    });
    if (w > max) max = w;
  }
  for (const r of rows) {
    r.t = Math.min(1, Math.max(0, r.weight / max));
    r.barW = Math.sqrt(r.t) * 100;
  }
  rows.sort((a, b) => b.weight - a.weight);
  return rows;
});

const topRows = computed(() => sortedRows.value.slice(0, 12));

const axisIds = computed(() => {
  const used = new Set<string>();
  for (const r of sortedRows.value) { used.add(r.from); used.add(r.to); }
  return Array.from(used).slice(0, 18);
});

function cellWeight(a: string, b: string): number {
  if (a === b) return 1;
  for (const r of sortedRows.value) {
    if ((r.from === a && r.to === b) || (r.from === b && r.to === a)) {
      const max = sortedRows.value.length ? sortedRows.value[0].weight : 1;
      return Math.min(1, r.weight / Math.max(0.0001, max));
    }
  }
  return 0;
}

/* 7-stop ramp from spec §12 */
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
  if (t <= 0)   return '#0a0e17';
  if (t >= 1)   return `rgb(${RAMP[RAMP.length - 1][1].join(',')})`;
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
.heat { padding: 4px 0 16px; }
.hh {
  color: var(--accent-warn);
  font-size: 13px;
  margin: 8px 0 4px;
  font-weight: 600;
}
.hint {
  color: var(--text-very-dim);
  font-size: 11px;
  margin-bottom: 8px;
  line-height: 1.5;
}

.bars { margin-bottom: 6px; }
.hm-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 5px;
}
.hm-space {
  width: 138px;
  font-size: 11px;
  color: var(--text-secondary);
  text-align: right;
}
.hm-bar-wrap {
  flex: 1;
  height: 18px;
  background: var(--bg-card);
  border-radius: 4px;
  position: relative;
  box-shadow: inset 0 0 0 1px var(--bg-elevated);
}
.hm-bar {
  display: block;
  height: 100%;
  border-radius: 4px;
  position: relative;
}
.hm-bar-label {
  position: absolute;
  left: 8px; top: 1px;
  font-size: 10.5px;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0,0,0,0.7);
}
.hm-num {
  width: 50px;
  color: var(--accent-warm-soft);
  font-size: 11.5px;
  font-family: Consolas, monospace;
}

.hm-grid-wrap {
  background: var(--bg-base);
  padding: 14px 12px 8px;
  border-radius: 8px;
  overflow-x: auto;
  box-shadow: inset 0 0 0 1px var(--bg-elevated);
}
.hm-grid { display: flex; flex-direction: column; gap: 1px; }
.hm-grid-row { display: flex; gap: 1px; align-items: center; }
.hm-grid-label {
  width: 56px;
  color: var(--text-secondary);
  font-size: 10.5px;
  text-align: right;
  padding-right: 4px;
  flex-shrink: 0;
}
.hm-axis-cell {
  width: 14px; height: 18px;
  font-size: 8.5px; color: var(--text-very-dim);
  text-align: center;
  writing-mode: vertical-lr;
  transform: rotate(180deg);
  font-family: Consolas, monospace;
}
.hm-grid-cell {
  width: 14px; height: 14px; border-radius: 2px;
  flex-shrink: 0;
  transition: transform .15s;
}
.hm-grid-cell:hover {
  transform: scale(1.4);
  outline: 1px solid #fff;
}

.cb-wrap {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px; font-size: 10px; color: var(--text-very-dim);
}
.cb-bar {
  flex: 1;
  height: 12px;
  border-radius: 3px;
  background: linear-gradient(
    90deg,
    rgb(13,18,39),
    rgb(40,11,84),
    rgb(101,21,110),
    rgb(165,44,96),
    rgb(222,73,65),
    rgb(248,142,35),
    rgb(252,230,110)
  );
  box-shadow: inset 0 0 0 1px var(--bg-elevated);
}
</style>
