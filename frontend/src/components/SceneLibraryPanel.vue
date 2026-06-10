<!--
  Scene library panel.
  Mirrors §10 of `docs/reference_ux_spec.md` ("Tab 3 — 场景库 / Scenes panel").

  - Header hint: total scenes & jump-to-NPC instruction.
  - Two filter rows: by space, by weather.
  - Scene cards with title / meta / trigger / participants / narrative / outcomes / tags.
-->
<template>
  <div class="scenes">
    <!-- ============== LIVE: runtime activity feed ============== -->
    <section class="live-block">
      <h3 class="block-title">
        📡 {{ lang.t('正在发生 · 实时活动', 'Happening Now · Live Activity') }}
      </h3>
      <div class="hint">
        {{ lang.t(
          `从 WS 事件流聚合，最近 ${liveActivity.length} 条事件。`,
          `Aggregated from the WS stream — latest ${liveActivity.length} events.`,
        ) }}
      </div>

      <div v-if="!liveActivity.length" class="placeholder">
        {{ lang.t('暂时风平浪静，等 NPC 做点什么…',
                 'All quiet for now — wait for the NPCs to act…') }}
      </div>

      <div v-for="(ev, i) in liveActivity" :key="`live${i}`"
           class="live-card" :class="`live-${ev.kind}`">
        <div class="live-head">
          <span class="live-time">{{ ev.time }}</span>
          <span class="live-tag">{{ ev.tagLabel }}</span>
          <span v-if="ev.loc" class="live-loc">@{{ ev.loc }}</span>
        </div>
        <div class="live-people" v-if="ev.peopleIds.length">
          <Chip v-for="pid in ev.peopleIds" :key="pid"
                variant="people" :clickable="true"
                @click="emit('jumpNpc', String(pid))">
            {{ npcLabel(pid) }}
          </Chip>
        </div>
        <div class="live-body">{{ ev.body }}</div>
      </div>
    </section>

    <!-- ============== Seeded scene library (collapsed) ============== -->
    <section class="scripted-block">
      <h3 class="block-title block-title--folded"
          :class="{ open: showScripted }"
          @click="showScripted = !showScripted">
        <span class="caret">{{ showScripted ? '▾' : '▸' }}</span>
        📚 {{ lang.t('剧本预设场景', 'Scripted Scenes') }}
        <span class="block-meta">
          {{ lang.t(`(${scenes.length} 条参考剧本，与运行时无关)`,
                    `(${scenes.length} reference scenes, not runtime-driven)`) }}
        </span>
      </h3>

      <div v-show="showScripted">
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
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import Chip from './Chip.vue';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';
import type { SceneEntry } from '@/api/endpoints';

const lang = useLangStore();
const events = useEventsStore();
const props = defineProps<{
  scenes: SceneEntry[];
  npcMap: Record<string, any>;
  /** Optional room name lookup (uid -> chinese name). */
  roomNameMap?: Record<string, string>;
}>();
const emit = defineEmits<{ (e: 'jumpNpc', id: string): void }>();

const spaceFilter   = ref<string>('all');
const weatherFilter = ref<string>('all');
const showScripted  = ref<boolean>(false);

/* ------------------------------------------------------------------ *
 * Live activity feed                                                  *
 * Built from the WS ring buffer:                                      *
 *   - `dialog`   -> "💬 NPC X ↔ NPC Y" card with the spoken line     *
 *   - `behavior` -> only emit when meaningful (move, ok=false, talk)  *
 *   - `day_summary` -> one big narrative card                         *
 * Limited to the most recent ~40 cards, newest first.                 *
 * ------------------------------------------------------------------ */
interface LiveCard {
  kind: 'dialog' | 'move' | 'fail' | 'narrator';
  time: string;
  loc?: string;
  peopleIds: string[];
  tagLabel: string;
  body: string;
}

function shortTime(iso?: string): string {
  if (!iso) return '';
  try { return iso.slice(11, 16); } catch { return ''; }
}
function roomName(uid?: string): string {
  if (!uid) return '';
  return props.roomNameMap?.[uid] || uid;
}

const liveActivity = computed<LiveCard[]>(() => {
  const out: LiveCard[] = [];
  for (const ev of events.stream) {
    const t = shortTime(ev.ts_sim);
    const p: any = ev.payload || {};
    if (ev.type === 'dialog') {
      const line = lang.lang === 'en'
        ? (p.speaker_line_en || p.speaker_line || '')
        : (p.speaker_line || p.speaker_line_en || '');
      const reply = lang.lang === 'en'
        ? (p.listener_line_en || p.listener_line || '')
        : (p.listener_line || p.listener_line_en || '');
      out.push({
        kind: 'dialog',
        time: t,
        loc: roomName(p.here_uid),
        peopleIds: [String(p.speaker_id || ''), String(p.listener_id || '')].filter(Boolean),
        tagLabel: lang.t('💬 对话', '💬 Talk'),
        body: line && reply ? `“${line}” ↩ “${reply}”` : (line || reply || ''),
      });
    } else if (ev.type === 'behavior') {
      const ok = p.ok !== false;
      if (p.action_id === 'move' && ok && p.params?.target_uid) {
        out.push({
          kind: 'move',
          time: t,
          loc: roomName(p.params.target_uid),
          peopleIds: [String(ev.agent_id || '')].filter(Boolean),
          tagLabel: lang.t('🚶 移动', '🚶 Move'),
          body: `${roomName(p.pre_state?.['agent.location_uid']) || '?'} → ${roomName(p.params.target_uid)}`,
        });
      } else if (!ok && p.action_id !== 'idle') {
        out.push({
          kind: 'fail',
          time: t,
          loc: roomName(p.here_uid),
          peopleIds: [String(ev.agent_id || '')].filter(Boolean),
          tagLabel: lang.t('⚠ 行动失败', '⚠ Action failed'),
          body: `${p.action_id}(${JSON.stringify(p.params || {})}) — ${p.note || ''}`,
        });
      }
    } else if (ev.type === 'day_summary') {
      const narr = lang.lang === 'en' ? (p.narrative_en || p.narrative_zh) : (p.narrative_zh || p.narrative_en);
      out.push({
        kind: 'narrator',
        time: t,
        peopleIds: [],
        tagLabel: `📜 ${p.day || ''}`,
        body: narr || '',
      });
    }
  }
  return out.reverse().slice(0, 40);
});

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
  border-radius: 0;
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

/* ---- live activity feed ---- */
.live-block { margin-bottom: 16px; }
.block-title {
  color: var(--accent-warn);
  font-weight: 600;
  font-size: 13.5px;
  margin: 6px 0;
}
.block-title--folded {
  cursor: pointer;
  user-select: none;
  color: var(--text-muted);
  background: rgba(255,255,255,0.02);
  padding: 6px 8px;
  border-radius: 0;
  display: flex; align-items: center; gap: 6px;
  border-top: 1px dashed var(--border-soft);
  margin-top: 16px;
}
.block-title--folded.open { color: var(--accent-warn); }
.block-title--folded:hover { background: rgba(255,255,255,0.05); }
.block-title--folded .caret { font-size: 11px; color: var(--text-very-dim); }
.block-title--folded .block-meta {
  color: var(--text-very-dim);
  font-size: 10.5px;
  font-weight: 400;
  margin-left: auto;
}

.live-card {
  background: var(--bg-card);
  padding: 8px 10px;
  border-radius: 0;
  border-left: 3px solid var(--accent-primary);
  margin-bottom: 6px;
}
.live-card.live-dialog   { border-left-color: #66BB6A; }
.live-card.live-move     { border-left-color: var(--accent-primary); }
.live-card.live-fail     { border-left-color: var(--accent-danger, #EF5350); }
.live-card.live-narrator {
  border-left-color: #FFD54F;
  background: rgba(255, 213, 79, 0.06);
}
.live-head {
  display: flex; gap: 8px; align-items: center;
  font-size: 11px;
  color: var(--text-very-dim);
  margin-bottom: 3px;
}
.live-time {
  color: var(--accent-warn);
  font-family: var(--font-mono);
  font-weight: 600;
}
.live-tag { color: var(--text-secondary); }
.live-loc { color: var(--text-very-dim); margin-left: auto; }
.live-people { margin: 4px 0; display: flex; flex-wrap: wrap; gap: 4px; }
.live-body {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
  white-space: pre-wrap;
}
</style>
