<!--
  Scene library panel.
  Mirrors §10 of `docs/reference_ux_spec.md` ("Tab 3 — 场景库 / Scenes panel").

  - Header hint: total scenes & jump-to-NPC instruction.
  - Two filter rows: by space, by weather.
  - Scene cards with title / meta / trigger / participants / narrative / outcomes / tags.
-->
<template>
  <div class="scenes">
    <div class="hint">
      {{ lang.t(
        `共 ${scenes.length} 个基础场景。点击参与者跳到 NPC。`,
        `${scenes.length} base scenes. Click any participant to jump to that NPC.`
      ) }}
    </div>

    <div class="filter-row">
      <span class="row-label">{{ lang.t('按空间', 'By space') }}</span>
      <Chip v-for="s in spaceOptions" :key="s.key"
            variant="filter" :clickable="true"
            :class="{ active: spaceFilter === s.key }"
            @click="spaceFilter = s.key">
        {{ s.label }}
      </Chip>
    </div>
    <div class="filter-row">
      <span class="row-label">{{ lang.t('按天气', 'By weather') }}</span>
      <Chip v-for="w in weatherOptions" :key="w.key"
            variant="filter" :clickable="true"
            :class="{ active: weatherFilter === w.key, [`weather-${w.key}`]: w.key !== 'all' }"
            @click="weatherFilter = w.key">
        {{ w.label }}
      </Chip>
    </div>

    <div class="hint">
      {{ lang.t('当前筛选', 'Showing') }}:
      <b style="color: var(--accent-warn)">{{ filtered.length }}</b>
      {{ lang.t('个场景', 'scenes') }}
    </div>

    <div v-for="sc in filtered" :key="String(sc.id)" class="scene-card">
      <div class="scene-title">{{ titleOf(sc) }}</div>
      <div class="scene-meta">
        <span v-if="sc.space_zh">📍 {{ lang.lang === 'en' ? (sc.space_en || sc.space_zh) : sc.space_zh }}</span>
        <span v-if="sc.time_band">  · 🕒 {{ sc.time_band }}</span>
        <span v-if="sc.weather"> · ☁ <span :class="`weather-${sc.weather}`">{{ sc.weather }}</span></span>
        <span v-if="sc.weekday_pattern"> · 📅 {{ sc.weekday_pattern }}</span>
      </div>
      <div v-if="triggerOf(sc)" class="scene-trigger">{{ triggerOf(sc) }}</div>
      <div class="scene-people" v-if="sc.people?.length">
        <Chip v-for="pid in sc.people" :key="pid"
              variant="people" :clickable="true"
              @click="emit('jumpNpc', String(pid))">
          {{ npcLabel(pid) }}
        </Chip>
      </div>
      <div class="scene-narr">{{ narrativeOf(sc) }}</div>

      <div v-if="sc.outcomes?.length" class="outcomes">
        <div class="outcomes-title">
          {{ lang.t('可能后果', 'Potential outcomes') }}:
        </div>
        <ul>
          <li v-for="(o, i) in sc.outcomes" :key="i">{{ o }}</li>
        </ul>
      </div>

      <div v-if="sc.tags?.length" class="tags-row">
        <Chip v-for="t in sc.tags" :key="t" variant="default">{{ t }}</Chip>
      </div>
    </div>

    <div v-if="!filtered.length" class="placeholder">
      {{ lang.t('当前筛选下没有场景。', 'No scenes match the current filter.') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import Chip from './Chip.vue';
import { useLangStore } from '@/stores/lang';
import type { SceneEntry } from '@/api/endpoints';

const lang = useLangStore();
const props = defineProps<{
  scenes: SceneEntry[];
  npcMap: Record<string, any>;
}>();
const emit = defineEmits<{ (e: 'jumpNpc', id: string): void }>();

const spaceFilter   = ref<string>('all');
const weatherFilter = ref<string>('all');

const spaceOptions = computed(() => {
  const set = new Set<string>();
  for (const s of props.scenes) if (s.space_zh) set.add(s.space_zh);
  return [
    { key: 'all', label: lang.t('全部', 'All') },
    ...Array.from(set).map(k => ({ key: k, label: k })),
  ];
});
const weatherOptions = computed(() => {
  const set = new Set<string>();
  for (const s of props.scenes) if (s.weather) set.add(s.weather);
  return [
    { key: 'all', label: lang.t('全部', 'All') },
    ...Array.from(set).map(k => ({ key: k, label: k })),
  ];
});

const filtered = computed(() => {
  return props.scenes.filter(s => {
    if (spaceFilter.value !== 'all' && s.space_zh !== spaceFilter.value) return false;
    if (weatherFilter.value !== 'all' && s.weather !== weatherFilter.value) return false;
    return true;
  });
});

function titleOf(s: SceneEntry): string {
  return lang.lang === 'en' ? (s.title_en || s.title || '') : (s.title || s.title_en || '');
}
function triggerOf(s: SceneEntry): string {
  return lang.lang === 'en' ? (s.trigger_en || s.trigger || '') : (s.trigger || s.trigger_en || '');
}
function narrativeOf(s: SceneEntry): string {
  return lang.lang === 'en' ? (s.narrative_en || s.narrative_zh || '') : (s.narrative_zh || s.narrative_en || '');
}
function npcLabel(id: string | number): string {
  const a = props.npcMap[String(id)];
  if (!a) return String(id);
  return lang.lang === 'en' ? (a.name_en || a.name || String(id)) : (a.name || a.name_en || String(id));
}
</script>

<style scoped>
.scenes { padding: 4px 0 16px; }
.placeholder { color: var(--text-disabled); padding: 18px 0; font-size: 12px; }
.hint {
  color: var(--text-very-dim);
  font-size: 11.5px;
  margin: 6px 0 8px;
}
.filter-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  margin-bottom: 4px;
}
.row-label {
  font-size: 11px;
  color: var(--text-very-dim);
  margin-right: 8px;
}

.scene-card {
  background: var(--bg-card);
  padding: 12px;
  border-radius: 8px;
  border-left: 3px solid var(--accent-warn);
  margin-bottom: 10px;
}
.scene-title {
  color: var(--accent-warm-soft);
  font-weight: 700;
  font-size: 14px;
}
.scene-meta {
  font-size: 11px;
  color: var(--text-very-dim);
  margin: 4px 0;
}
.scene-trigger {
  color: var(--text-dim);
  font-style: italic;
  font-size: 11px;
  margin-bottom: 4px;
}
.scene-people { margin: 6px 0; }
.scene-narr {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.outcomes { margin-top: 6px; font-size: 11.5px; }
.outcomes-title { color: var(--text-very-dim); margin-bottom: 2px; }
.outcomes ul { padding-left: 18px; color: var(--text-secondary); }
.tags-row { margin-top: 6px; }

.weather-clear   { color: #ffd54f; }
.weather-rain    { color: #4fc3f7; }
.weather-overcast{ color: #90a4ae; }
.weather-hot     { color: #ff7043; }
.weather-cold    { color: #80deea; }
.weather-snow    { color: #e1f5fe; }
</style>
