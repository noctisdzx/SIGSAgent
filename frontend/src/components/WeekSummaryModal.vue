<!--
  Weekly space-evaluation modal.

  Pops (non-blocking) on ISO-week rollover or the manual "Weekly review" button.
  Lists every agent's first-person evaluation of the building/space for the
  week, with the new features they wish for (wants) and the spots that felt bad
  (pain points). Driven by `sim.pendingWeekSummary`.
-->
<template>
  <transition name="fade">
    <div v-if="sim.pendingWeekSummary" class="wsm-backdrop" @click.self="onClose">
      <div class="wsm">
        <header class="wsm-head">
          <div class="wsm-head-text">
            <span class="wsm-badge">{{ lang.t('每周空间体验回访', 'Weekly Space Review') }}</span>
            <h2 class="wsm-title">{{ lang.t('居民对当前建筑空间的评价', 'Residents’ take on the space') }}</h2>
            <div class="wsm-sub">
              <span class="wsm-week">{{ summary.week }}</span>
              <span class="wsm-when">· {{ summary.n_agents || agents.length }} {{ lang.t('位居民', 'residents') }}</span>
            </div>
          </div>
          <button class="wsm-close" @click="onClose" :title="lang.t('关闭', 'Close')">×</button>
        </header>

        <section class="wsm-body">
          <div class="wsm-toolbar">
            <input
              v-model="q"
              class="wsm-search"
              :placeholder="lang.t('搜索居民 / 地点 / 关键词…', 'Search resident / place / keyword…')"
            />
          </div>

          <div v-if="!filtered.length" class="wsm-empty">
            {{ lang.t('暂无匹配的评价。', 'No matching evaluations.') }}
          </div>

          <article v-for="a in filtered" :key="a.id" class="wsm-card">
            <div class="wsm-card-head">
              <span class="wsm-name">{{ nameOf(a) }}</span>
              <span v-if="a.role" class="wsm-role">{{ a.role }}</span>
              <span v-if="a.favorite_place" class="wsm-fav">★ {{ a.favorite_place }}</span>
              <span v-if="a.degraded" class="wsm-degraded">{{ lang.t('降级', 'degraded') }}</span>
            </div>
            <p v-if="evalOf(a)" class="wsm-eval">{{ evalOf(a) }}</p>

            <div class="wsm-tags">
              <div v-if="(a.wants || []).length" class="wsm-want">
                <span class="wsm-tag-label">💡 {{ lang.t('想要的新功能', 'Wishes') }}</span>
                <ul><li v-for="(w, i) in a.wants" :key="i">{{ w }}</li></ul>
              </div>
              <div v-if="(a.pain_points || []).length" class="wsm-pain">
                <span class="wsm-tag-label">⚠ {{ lang.t('体验不好的地方', 'Pain points') }}</span>
                <ul><li v-for="(p, i) in a.pain_points" :key="i">{{ p }}</li></ul>
              </div>
            </div>
          </article>
        </section>

        <footer class="wsm-foot">
          <span class="wsm-foot-note">{{ lang.t('该回访不会暂停模拟', 'This review does not pause the sim') }}</span>
          <button class="wsm-secondary" @click="onClose">{{ lang.t('关闭', 'Close') }}</button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useLangStore } from '@/stores/lang';
import { useSimStore, type WeekAgentEval } from '@/stores/sim';

const lang = useLangStore();
const sim = useSimStore();
const q = ref('');

const summary = computed(() => sim.pendingWeekSummary || ({ agents: [] } as any));
const agents = computed<WeekAgentEval[]>(() => summary.value.agents || []);

function nameOf(a: WeekAgentEval): string {
  return lang.lang === 'en' ? (a.name_en || a.name || a.id) : (a.name || a.name_en || a.id);
}
function evalOf(a: WeekAgentEval): string {
  const zh = a.evaluation_zh || '';
  const en = a.evaluation_en || '';
  return (lang.lang === 'en' ? (en || zh) : (zh || en)).trim();
}

const filtered = computed<WeekAgentEval[]>(() => {
  const term = q.value.trim().toLowerCase();
  if (!term) return agents.value;
  return agents.value.filter(a => {
    const hay = [
      a.name, a.name_en, a.role, a.favorite_place,
      a.evaluation_zh, a.evaluation_en,
      ...(a.wants || []), ...(a.pain_points || []),
    ].join(' ').toLowerCase();
    return hay.includes(term);
  });
});

function onClose() { sim.dismissWeekSummary(); }
</script>

<style scoped>
.wsm-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.62);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  backdrop-filter: blur(2px);
}
.wsm {
  width: min(860px, 94vw);
  max-height: 90vh;
  background: var(--bg-panel);
  border: 1px solid var(--border-soft);
  border-radius: 0;
  box-shadow: 0 20px 60px rgba(0,0,0,0.55);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.wsm-head {
  padding: 16px 22px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 14px;
}
.wsm-head-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.wsm-badge {
  color: var(--accent-good-soft, #66BB6A);
  font-weight: 700; letter-spacing: 0.5px; font-size: 11.5px; text-transform: uppercase;
}
.wsm-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--text-primary); line-height: 1.35; }
.wsm-sub { display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px; color: var(--text-very-dim); }
.wsm-week { font-family: var(--font-mono); color: var(--text-secondary); }
.wsm-close { background: none; border: none; color: var(--text-very-dim); font-size: 22px; cursor: pointer; padding: 0 8px; flex: 0 0 auto; }
.wsm-close:hover { color: var(--accent-warn); }

.wsm-body { padding: 14px 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; }
.wsm-toolbar { position: sticky; top: 0; }
.wsm-search {
  width: 100%; box-sizing: border-box;
  background: var(--bg-card); color: var(--text-primary);
  border: 1px solid var(--border-soft); border-radius: 0;
  padding: 7px 12px; font-size: 13px; outline: none;
}
.wsm-search:focus { border-color: var(--accent-good-soft, #66BB6A); }
.wsm-empty { color: var(--text-very-dim); font-size: 13px; text-align: center; padding: 24px 0; }

.wsm-card {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: 0;
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.wsm-card-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.wsm-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.wsm-role { font-size: 11.5px; color: var(--text-very-dim); }
.wsm-fav { font-size: 11.5px; color: var(--accent-warn, #ffc452); margin-left: auto; }
.wsm-degraded { font-size: 10.5px; color: var(--accent-danger); }

.wsm-eval { margin: 0; font-size: 13.5px; line-height: 1.75; color: var(--text-secondary); }

.wsm-tags { display: flex; flex-wrap: wrap; gap: 14px; }
.wsm-want, .wsm-pain { flex: 1 1 240px; min-width: 220px; }
.wsm-tag-label { display: block; font-size: 11px; font-weight: 600; margin-bottom: 4px; }
.wsm-want .wsm-tag-label { color: var(--accent-good-soft, #66BB6A); }
.wsm-pain .wsm-tag-label { color: var(--accent-warn, #ffc452); }
.wsm-tags ul { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.7; color: var(--text-secondary); }
.wsm-tags li + li { margin-top: 1px; }

.wsm-foot {
  padding: 12px 22px;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border-soft);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}
.wsm-foot-note { font-size: 11.5px; color: var(--text-very-dim); }
.wsm-secondary {
  padding: 8px 18px; border-radius: 0; font-size: 13px; cursor: pointer;
  border: 1px solid var(--border-soft); background: var(--bg-card); color: var(--text-secondary);
}
.wsm-secondary:hover { color: var(--text-primary); }

.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
