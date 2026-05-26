<!--
  STM/LTM lists with tone-colored left border + hit_count badge + degraded badge.
  Tone palette mirrors §17 of `docs/reference_ux_spec.md`.
-->
<template>
  <div class="memory-panel">
    <section>
      <h3>{{ lang.t('短期记忆 (STM)', 'Short-Term Memory') }} · {{ stm.length }}</h3>
      <div v-if="!stm.length" class="empty">{{ lang.t('（暂无）', '(empty)') }}</div>
      <div v-for="m in stm" :key="m.id || m.ts" class="mem-item" :style="{ borderLeftColor: tone(m.tone) }">
        <div class="meta">
          <span>{{ m.ts }}</span>
          <span class="hit">hit ×{{ m.hit_count ?? 0 }}</span>
        </div>
        <div class="text">{{ memText(m) }}</div>
      </div>
    </section>
    <section>
      <h3>{{ lang.t('长期记忆 (LTM)', 'Long-Term Memory') }} · {{ ltm.length }}</h3>
      <div v-if="!ltm.length" class="empty">{{ lang.t('（暂无）', '(empty)') }}</div>
      <div v-for="m in ltm" :key="m.id || m.ts" class="mem-item" :style="{ borderLeftColor: tone(m.tone) }">
        <div class="meta">
          <span>{{ m.ts }}</span>
          <span class="hit">hit ×{{ m.hit_count ?? 0 }}</span>
          <span v-if="m.degraded" class="degraded">degraded</span>
        </div>
        <div class="text">{{ memText(m) }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useLangStore } from '@/stores/lang';
const lang = useLangStore();

defineProps<{ stm: any[]; ltm: any[] }>();

const TONE_MAP: Record<string, string> = {
  warm:     '#ffa726',
  tense:    '#ef5350',
  focused:  '#26c6da',
  casual:   '#78909c',
  curious:  '#ce93d8',
  gentle:   '#a5d6a7',
  playful:  '#fff176',
  decisive: '#ff8a65',
};
function tone(t?: string): string { return (t && TONE_MAP[t]) || '#42a5f5'; }
function memText(m: any): string {
  if (!m) return '';
  if (lang.lang === 'en') return m.text_en || m.text || '';
  return m.text || m.text_en || '';
}
</script>

<style scoped>
.memory-panel { padding: 12px; }
.memory-panel h3 { color: var(--accent-warm-soft); font-size: 13px; margin: 10px 0 6px; }
.mem-item {
  background: var(--bg-card);
  border-left: 3px solid var(--tone-default);
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 4px;
}
.meta {
  display: flex; gap: 8px; font-size: 10.5px; color: var(--text-very-dim); margin-bottom: 2px;
  justify-content: space-between;
}
.hit { color: var(--accent-warn); }
.degraded { color: var(--accent-danger-soft); }
.text { font-size: 12.5px; color: var(--text-secondary); line-height: 1.5; }
.empty { color: var(--text-disabled); font-size: 12px; padding: 4px 0; }
</style>
