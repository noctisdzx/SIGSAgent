<!--
  Relation (edge) detail panel.
  See §9 of `docs/reference_ux_spec.md` ("Tab 2 — 关系/Edge panel").
-->
<template>
  <div v-if="!edge" class="placeholder">
    {{ lang.t(
      '在图谱中点击一条关系连线以查看详情。',
      'Click an edge in the graph to inspect a relation.'
    ) }}
  </div>
  <div v-else class="rel">
    <div class="npc-name">
      <span class="from"  @click="emit('jumpNpc', String(fromId))">{{ fromName }}</span>
      <span class="bond">⇌</span>
      <span class="to"    @click="emit('jumpNpc', String(toId))">{{ toName }}</span>
    </div>
    <div class="npc-role">{{ label }}</div>

    <div class="em-summary">
      <div class="em-row">
        <span class="em-stat"><b :style="{ color: weightColor }">{{ weight.toFixed(2) }}</b>
          {{ lang.t('权重 / weight', 'weight') }}</span>
        <span class="em-stat"><b>{{ tone }}</b> {{ lang.t('主基调 / tone', 'tone') }}</span>
        <span class="em-stat color-sample">
          <span class="dot" :style="{ background: color }"></span>
          <span class="hex">{{ color }}</span>
        </span>
      </div>
      <div class="em-text">{{ summaryText }}</div>
    </div>

    <div class="empty-hint" v-if="!hasInteraction">
      {{ lang.t(
        '本周这两人没有产生记录在案的互动。',
        'No recorded interaction between them this week.'
      ) }}
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
  edge: RelationEdge | null;
  /** Map of agent.id (as string) → agent record. Used for from/to names. */
  npcMap: Record<string, any>;
}>();

const emit = defineEmits<{ (e: 'jumpNpc', id: string): void }>();

const ft = computed(() => (props.edge ? edgeFromTo(props.edge) : { from: '', to: '' }));
const fromId = computed(() => ft.value.from);
const toId   = computed(() => ft.value.to);

function nameOf(id: string): string {
  const n = props.npcMap[id];
  if (!n) return id;
  return lang.lang === 'en' ? (n.name_en || n.name || id) : (n.name || n.name_en || id);
}
const fromName = computed(() => nameOf(fromId.value));
const toName   = computed(() => nameOf(toId.value));

const label = computed(() => {
  if (!props.edge) return '';
  return lang.lang === 'en'
    ? (props.edge.label_en || props.edge.label || '')
    : (props.edge.label || props.edge.label_en || '');
});
const color = computed(() => props.edge?.color || '#90caf9');
const tone  = computed(() => props.edge?.tone || '—');
const weight = computed(() => Number(props.edge?.weight ?? 0));
const weightColor = computed(() => {
  if (weight.value > 0.7) return 'var(--accent-good-soft)';
  if (weight.value < 0.4) return 'var(--accent-danger-soft)';
  return 'var(--text-secondary)';
});

const summaryText = computed(() => {
  if (!props.edge) return '';
  return lang.t(
    `两人之间的关系类型为「${label.value}」，整体基调 ${tone.value}，权重 ${weight.value.toFixed(2)}。`,
    `Relation kind: "${label.value}". Overall tone: ${tone.value}. Weight: ${weight.value.toFixed(2)}.`,
  );
});

const hasInteraction = computed(() => Boolean(props.edge && (props.edge as any).triplets?.length));
</script>

<style scoped>
.rel { padding: 4px 0 16px; }
.placeholder {
  color: var(--text-disabled);
  text-align: center;
  padding: 40px 12px;
  font-size: 12.5px;
  line-height: 1.7;
}
.npc-name {
  color: var(--accent-primary);
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 2px;
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
}
.npc-name .from, .npc-name .to {
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 4px;
}
.npc-name .from:hover, .npc-name .to:hover { color: #fff; }
.npc-name .bond {
  color: var(--accent-warn);
  font-weight: 400;
}
.npc-role {
  color: var(--text-very-dim);
  font-size: 13px;
  margin-bottom: 12px;
}

.em-summary {
  background: var(--bg-card);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.em-row {
  display: flex; flex-wrap: wrap; gap: 14px;
  font-size: 11px; color: var(--text-very-dim);
  margin-bottom: 8px;
}
.em-stat b { font-size: 12.5px; color: var(--text-primary); margin-right: 4px; }
.em-text { line-height: 1.7; }
.color-sample { display: inline-flex; align-items: center; gap: 6px; }
.color-sample .dot {
  width: 12px; height: 12px; border-radius: 50%;
  border: 1px solid #fff3;
}
.color-sample .hex {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
  color: var(--text-muted);
}

.empty-hint {
  margin-top: 12px;
  color: var(--text-disabled);
  font-size: 12px;
  font-style: italic;
}
</style>
