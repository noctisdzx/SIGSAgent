<!--
  Day-summary modal.
  Appears automatically whenever the backend rolls midnight and the SimLoop
  emits a `day_summary` WS event. The sim is server-side paused at that
  moment; clicking "Start next day" calls /api/sim/start and dismisses.
-->
<template>
  <transition name="fade">
    <div v-if="sim.pendingSummary" class="dsm-backdrop" @click.self="onCloseRequested">
      <div class="dsm">
        <header class="dsm-head">
          <h2>
            <span class="dsm-badge">{{ lang.t('上帝视角旁白', "Narrator's Recap") }}</span>
            <span class="dsm-day">{{ summary.day }}</span>
          </h2>
          <button class="dsm-close" @click="onCloseRequested" :title="lang.t('关闭', 'Close')">×</button>
        </header>

        <section class="dsm-body">
          <p class="dsm-narrative">{{ narrativeText }}</p>

          <div v-if="summary.stats" class="dsm-stats">
            <span class="dsm-stat">
              <b>{{ summary.stats.n_agents ?? '?' }}</b>
              {{ lang.t('NPC 在场', 'NPCs on stage') }}
            </span>
            <span class="dsm-stat">
              <b>{{ summary.stats.n_behaviors ?? 0 }}</b>
              {{ lang.t('次行为', 'actions') }}
            </span>
            <span class="dsm-stat">
              <b>{{ summary.stats.n_dialogs ?? 0 }}</b>
              {{ lang.t('段对话', 'dialogs') }}
            </span>
            <span v-if="summary.degraded" class="dsm-stat dsm-warn">
              {{ lang.t('⚠ LLM 降级', '⚠ LLM degraded') }}
            </span>
          </div>
        </section>

        <footer class="dsm-foot">
          <button class="dsm-secondary" @click="onCloseRequested">
            {{ lang.t('关闭（保持暂停）', 'Close (stay paused)') }}
          </button>
          <button class="dsm-primary" @click="startNextDay">
            ▶ {{ lang.t('开启下一天', 'Start next day') }}
          </button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLangStore } from '@/stores/lang';
import { useSimStore } from '@/stores/sim';

const lang = useLangStore();
const sim = useSimStore();

const summary = computed(() => sim.pendingSummary || {} as any);
const narrativeText = computed(() => {
  const s = sim.pendingSummary;
  if (!s) return '';
  if (lang.lang === 'en') return s.narrative_en || s.narrative_zh || '';
  return s.narrative_zh || s.narrative_en || '';
});

async function startNextDay() {
  await sim.startNextDay();
}
function onCloseRequested() {
  // Just dismiss the modal; sim stays paused so the user can still click
  // the "Resume" button in the top bar when ready.
  sim.dismissSummary();
}
</script>

<style scoped>
.dsm-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.62);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  backdrop-filter: blur(2px);
}
.dsm {
  width: min(720px, 92vw);
  max-height: 86vh;
  background: var(--bg-panel);
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.55);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.dsm-head {
  padding: 16px 22px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
  display: flex; align-items: center; justify-content: space-between;
}
.dsm-head h2 {
  margin: 0; font-size: 16px;
  display: flex; align-items: baseline; gap: 12px;
}
.dsm-badge {
  color: var(--accent-warn);
  font-weight: 700;
  letter-spacing: 0.5px;
}
.dsm-day { color: var(--text-secondary); font-family: Consolas, monospace; font-size: 13px; }
.dsm-close {
  background: none; border: none;
  color: var(--text-very-dim);
  font-size: 22px;
  cursor: pointer;
  padding: 0 8px;
}
.dsm-close:hover { color: var(--accent-warn); }

.dsm-body {
  padding: 20px 24px;
  overflow-y: auto;
  flex: 1;
  display: flex; flex-direction: column; gap: 16px;
}
.dsm-narrative {
  color: var(--text-primary);
  font-size: 14.5px;
  line-height: 1.85;
  white-space: pre-wrap;
  margin: 0;
}
.dsm-stats {
  display: flex; flex-wrap: wrap; gap: 14px;
  border-top: 1px dashed var(--border-soft);
  padding-top: 12px;
  font-size: 11.5px;
  color: var(--text-very-dim);
}
.dsm-stat b { color: var(--accent-warm-soft); margin-right: 4px; }
.dsm-warn { color: var(--accent-danger); }

.dsm-foot {
  padding: 12px 22px;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border-soft);
  display: flex; justify-content: flex-end; gap: 10px;
}
.dsm-secondary, .dsm-primary {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid var(--border-soft);
}
.dsm-secondary {
  background: var(--bg-card); color: var(--text-secondary);
}
.dsm-secondary:hover { color: var(--text-primary); }
.dsm-primary {
  background: var(--accent-good-soft, #66BB6A); color: #0a0e17; font-weight: 600;
  border-color: transparent;
}
.dsm-primary:hover { filter: brightness(1.1); }

.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
