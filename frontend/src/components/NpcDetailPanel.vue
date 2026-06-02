<!--
  NPC detail panel.
  Mirrors §8 of `docs/reference_ux_spec.md` ("Tab 1 — NPC panel").
  Sections rendered top-to-bottom:
    name  ·  role
    📋 基础身份 / Basic Identity
    🧬 静态层 · 人格底色
    🎭 双层人格
    🔄 动态层 · 当前状态
    🏠 生活方式
    📅 今日日程表 (preview)
-->
<template>
  <div v-if="!npc" class="placeholder">
    {{ lang.t(
      '点击图谱中的节点查看 NPC 完整画像、文化身份与本周记忆',
      'Click a node to see NPC profile, cultural identity & memory.'
    ) }}
  </div>
  <div v-else class="npc">
    <div class="npc-name">{{ name }}</div>
    <div class="npc-role">{{ role }}</div>

    <!-- 基础身份 -->
    <div class="section-title">{{ lang.t('📋 基础身份', '📋 Basic Identity') }}</div>
    <div class="kv"><span class="k">{{ lang.t('年龄', 'Age') }}</span>
      <span class="v">{{ age || '—' }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('院系', 'Major') }}</span>
      <span class="v">{{ major || '—' }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('分组', 'Group') }}</span>
      <span class="tag" :style="groupChipStyle">{{ groupLabel }}</span></div>

    <!-- 静态层 · 人格底色 -->
    <div class="section-title">
      {{ lang.t('🧬 静态层 · 人格底色', '🧬 Static · Personality Base') }}
    </div>
    <div class="kv"><span class="k">{{ lang.t('先天特质', 'Innate trait') }}</span>
      <span class="v">{{ pick('innate') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('后天特质', 'Learned trait') }}</span>
      <span class="v">{{ pick('learned') }}</span></div>
    <div class="kv"><span class="k">MBTI</span>
      <span class="tag mbti">{{ profile.mbti || '—' }}</span></div>
    <div class="kv"><span class="k">OCEAN</span>
      <span class="v mono">{{ profile.ocean || '—' }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('信念', 'Belief') }}</span>
      <span class="v">{{ pick('belief') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('长期目标', 'Long-term goal') }}</span>
      <span class="v">{{ pick('goal') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('核心矛盾', 'Core contradiction') }}</span>
      <span class="v contradiction">{{ pick('contradiction') }}</span></div>

    <!-- 双层人格 -->
    <div class="section-title">{{ lang.t('🎭 双层人格', '🎭 Dual Persona') }}</div>
    <div class="kv"><span class="k">{{ lang.t('表层', 'Surface') }}</span>
      <span class="v">{{ pick('surface') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('深层', 'Deep') }}</span>
      <span class="v deep">{{ pick('deep') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('核心恐惧', 'Core fear') }}</span>
      <span class="v fear">{{ pick('fear') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('核心渴望', 'Core desire') }}</span>
      <span class="v desire">{{ pick('desire') }}</span></div>

    <!-- 动态层 · 当前状态 -->
    <div class="section-title">
      {{ lang.t('🔄 动态层 · 当前状态', '🔄 Dynamic · Current State') }}
    </div>
    <div class="kv" v-if="pick('long_desire')">
      <span class="k">{{ lang.t('长期欲望', 'Long desire') }}</span>
      <span class="v">{{ pick('long_desire') }}</span>
    </div>
    <div class="kv" v-if="pick('short_goal')">
      <span class="k">{{ lang.t('短期目标', 'Short goal') }}</span>
      <span class="v">{{ pick('short_goal') }}</span>
    </div>
    <div class="kv" v-if="pick('constraint')">
      <span class="k">{{ lang.t('当前约束', 'Constraint') }}</span>
      <span class="v">{{ pick('constraint') }}</span>
    </div>
    <div class="kv" v-if="pick('bias')">
      <span class="k">{{ lang.t('感知偏差', 'Bias') }}</span>
      <span class="v bias">{{ pick('bias') }}</span>
    </div>
    <div class="kv narrative" v-if="pick('narrative')">
      «{{ pick('narrative') }}»
    </div>

    <!-- 生活方式 -->
    <div class="section-title">{{ lang.t('🏠 生活方式', '🏠 Lifestyle') }}</div>
    <div class="kv"><span class="k">{{ lang.t('作息', 'Lifestyle') }}</span>
      <span class="v">{{ pick('lifestyle') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('日常节律', 'Rhythm') }}</span>
      <span class="v">{{ pick('rhythm') }}</span></div>
    <div class="kv"><span class="k">{{ lang.t('常见空间', 'Common spaces') }}</span>
      <span class="v">{{ pick('spaces') }}</span></div>

    <!-- 今日日程 -->
    <div class="section-title" v-if="scheduleRows.length">
      {{ lang.t('📅 今日日程表', '📅 Today\'s Schedule') }}
    </div>
    <div class="schedule-wrap" v-if="scheduleRows.length">
      <div v-for="(s, i) in scheduleRows" :key="i" class="sch-item">
        <span class="sch-time">{{ s.time }}</span>
        <span class="sch-act">{{ s.act }}</span>
      </div>
    </div>

    <!-- 当前位置 -->
    <div class="kv loc" v-if="locationLabel">
      <span class="k">{{ lang.t('当前位置', 'Location') }}</span>
      <span class="v">{{ locationLabel }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';

const lang = useLangStore();

const props = defineProps<{
  npc: any | null;
  /** colors keyed by group_zh; lets the group chip tint match the graph node. */
  groupColorMap?: Record<string, string>;
  /** optional readable location string. */
  locationLabel?: string;
}>();

const profile = computed<any>(() => props.npc?.profile || props.npc || {});

function pick(field: string): string {
  if (!props.npc) return '';
  // Persona JSON uses bilingual suffixes (`field_zh` / `field_en`); when no
  // suffix exists the bare `field` is treated as Chinese-by-default. We must
  // try the language-suffixed key FIRST in both directions — the previous
  // version only added the `_en` candidate, so Chinese mode always missed
  // every `*_zh` field and rendered blank.
  const preferred = lang.lang === 'en' ? '_en' : '_zh';
  const fallback  = lang.lang === 'en' ? '_zh' : '_en';
  const candidates = [
    profile.value[field + preferred],
    props.npc[field + preferred],
    profile.value[field],
    props.npc[field],
    profile.value[field + fallback],
    props.npc[field + fallback],
  ];
  for (const c of candidates) {
    if (c !== undefined && c !== null && c !== '') return String(c);
  }
  return '';
}

const name = computed(() => {
  if (!props.npc) return '';
  // `profile.name_zh / name_en` is the authoritative bilingual pair from the
  // persona JSON; the top-level `name` mirrors the Chinese one but may be
  // missing in older mock data, so we fall through to the id as a last resort.
  return lang.lang === 'en'
    ? (profile.value.name_en || props.npc.name_en || profile.value.name_zh
        || props.npc.name || String(props.npc.id || ''))
    : (profile.value.name_zh || props.npc.name || profile.value.name_en
        || props.npc.name_en || String(props.npc.id || ''));
});
const role = computed(() => {
  if (!props.npc) return '';
  // CAVEAT: top-level `npc.role` is the machine code (e.g.
  // "undergraduate_literature"); the human-readable role lives in
  // `profile.role_zh / role_en`. The old code returned the code in Chinese
  // mode because it only checked `npc.role`.
  return lang.lang === 'en'
    ? (profile.value.role_en || profile.value.role_zh || props.npc.role_en || props.npc.role || '')
    : (profile.value.role_zh || profile.value.role_en || props.npc.role || props.npc.role_en || '');
});
const major = computed(() => {
  if (!props.npc) return '';
  const z = profile.value.major_zh || profile.value.major || props.npc.major;
  const e = profile.value.major_en || props.npc.major_en;
  return lang.lang === 'en' ? (e || z || '') : (z || e || '');
});
const age = computed(() => {
  const a = profile.value.age ?? props.npc?.age;
  if (a === undefined || a === null || a === '') return '';
  return lang.lang === 'en' ? `${a} y/o` : `${a} 岁`;
});
const groupLabel = computed(() => {
  if (!props.npc) return '';
  if (lang.lang === 'en') {
    return profile.value.group_en || props.npc.group_en || profile.value.group || props.npc.group || '';
  }
  return profile.value.group_zh || profile.value.group || props.npc.group || props.npc.group_zh || '';
});
const groupColor = computed<string>(() => {
  const key = profile.value.group_zh || profile.value.group || props.npc?.group_zh || props.npc?.group;
  return (props.groupColorMap && key && props.groupColorMap[key]) || props.npc?.color || '#90caf9';
});
const groupChipStyle = computed(() => ({
  background: groupColor.value + '22',
  color: groupColor.value,
}));

const scheduleRows = computed(() => {
  const raw = profile.value.schedule || props.npc?.schedule;
  if (!raw) return [];
  // schedule may be a list of strings ("07:30 …") or a list of structured rows.
  const lines: string[] = Array.isArray(raw)
    ? raw.map((r: any) => typeof r === 'string' ? r : `${r.start || r.time || ''} ${r.activity || r.act || ''}`)
    : typeof raw === 'string'
      ? raw.split('|').map(s => s.trim()).filter(Boolean)
      : [];
  return lines.map(line => {
    const m = line.match(/^(\S+)\s+(.*)$/);
    return m ? { time: m[1], act: m[2] } : { time: '·', act: line };
  });
});
</script>

<style scoped>
.npc { padding: 4px 0 16px; }
.placeholder {
  color: var(--text-disabled);
  text-align: center;
  padding: 40px 12px;
  font-size: 12.5px;
  line-height: 1.7;
}

.npc-name {
  color: var(--accent-primary);
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 2px;
}
.npc-role {
  color: var(--text-very-dim);
  font-size: 13px;
  margin-bottom: 6px;
}

.kv {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-secondary);
  margin: 4px 0;
  align-items: baseline;
  line-height: 1.55;
}
.kv .k { color: var(--text-very-dim); min-width: 80px; flex-shrink: 0; font-size: 11.5px; }
.kv .v { color: var(--text-secondary); flex: 1; }
.kv .v.contradiction { color: var(--accent-danger-soft); }
.kv .v.deep          { color: var(--accent-purple-soft); }
.kv .v.fear          { color: var(--accent-danger-soft); }
.kv .v.desire        { color: var(--accent-good-soft); }
.kv .v.bias          { color: var(--accent-warm-soft); }
.kv.narrative {
  color: var(--accent-cyan-soft);
  font-style: italic;
  margin-top: 8px;
  padding: 6px 10px;
  background: var(--bg-card);
  border-radius: 6px;
}
.kv.loc { margin-top: 12px; }

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.tag.mbti {
  background: var(--bg-elevated-hover);
  color: var(--accent-primary);
}

.mono { font-family: Consolas, 'Courier New', monospace; font-size: 11.5px; }

.schedule-wrap {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 12px;
  margin-top: 8px;
}
.sch-item {
  display: flex;
  gap: 12px;
  font-size: 12px;
  padding: 3px 0;
  border-bottom: 1px dashed var(--border-soft);
}
.sch-item:last-child { border-bottom: none; }
.sch-time {
  min-width: 60px;
  color: var(--accent-warn);
  font-weight: 600;
  font-family: Consolas, 'Courier New', monospace;
}
.sch-act { color: var(--text-muted); }
</style>
