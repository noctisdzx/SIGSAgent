<!--
  Day-summary modal — short-story layout.

  Appears automatically on midnight rollover (sim is paused), and on the
  manual "Recap now" button (sim stays running). Renders an LLM-authored
  short story with title, protagonist card, supporting cast chips,
  multi-paragraph narrative, a one-paragraph synopsis and a teaser of
  what tomorrow might bring.
-->
<template>
  <transition name="fade">
    <div v-if="sim.pendingSummary" class="dsm-backdrop" @click.self="onCloseRequested">
      <div class="dsm">
        <header class="dsm-head">
          <div class="dsm-head-text">
            <span class="dsm-badge">{{ lang.t('上帝视角 · 短篇旁白', "Narrator's Short Story") }}</span>
            <h2 class="dsm-title">{{ titleText || lang.t('未命名章节', 'Untitled Chapter') }}</h2>
            <div class="dsm-sub">
              <span class="dsm-day">{{ summary.day }}</span>
              <span v-if="summary.ts_sim" class="dsm-when">
                · {{ lang.t('截至', 'as of') }} {{ shortTs(summary.ts_sim) }}
              </span>
              <span v-if="summary.degraded" class="dsm-warn">
                · {{ lang.t('⚠ LLM 降级（占位短篇）', '⚠ LLM degraded (placeholder)') }}
              </span>
            </div>
          </div>
          <button class="dsm-close" @click="onCloseRequested" :title="lang.t('关闭', 'Close')">×</button>
        </header>

        <section class="dsm-body">
          <!-- Protagonist + supporting cast -->
          <div v-if="protagonistName || supportingCast.length" class="dsm-cast">
            <div v-if="protagonistName" class="dsm-protagonist">
              <span class="dsm-cast-label">{{ lang.t('主人公', 'Protagonist') }}</span>
              <div class="dsm-proto-card">
                <span class="dsm-proto-name">{{ protagonistName }}</span>
                <span v-if="protagonistWhy" class="dsm-proto-why">{{ protagonistWhy }}</span>
              </div>
            </div>
            <div v-if="supportingCast.length" class="dsm-supporting">
              <span class="dsm-cast-label">{{ lang.t('配角', 'Supporting Cast') }}</span>
              <ul class="dsm-cast-list">
                <li v-for="(c, i) in supportingCast" :key="i" class="dsm-cast-chip">
                  <span class="dsm-chip-name">{{ c.name }}</span>
                  <span v-if="c.role" class="dsm-chip-role">— {{ c.role }}</span>
                </li>
              </ul>
            </div>
          </div>

          <!-- Multi-paragraph short story -->
          <article v-if="storyParagraphs.length" class="dsm-story">
            <p v-for="(para, i) in storyParagraphs" :key="i" class="dsm-para">{{ para }}</p>
          </article>
          <!-- Fallback: just the one-paragraph synopsis if no story present -->
          <p v-else class="dsm-para">{{ narrativeText }}</p>

          <!-- TL;DR shown only when no full story is available (e.g. LLM degraded). -->
          <div v-if="!storyParagraphs.length && narrativeText" class="dsm-synopsis">
            <span class="dsm-synopsis-label">{{ lang.t('一句话梗概', 'TL;DR') }}</span>
            <p>{{ narrativeText }}</p>
          </div>

          <!-- Tomorrow predictions -->
          <div v-if="tomorrowLines.length" class="dsm-tomorrow">
            <span class="dsm-tomorrow-label">
              🔮 {{ lang.t('明日预测', 'Tomorrow may bring') }}
            </span>
            <ul>
              <li v-for="(line, i) in tomorrowLines" :key="i">{{ line }}</li>
            </ul>
          </div>

          <!-- Stats footer -->
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
            <span class="dsm-stat">
              <b>{{ summary.stats.n_memories ?? 0 }}</b>
              {{ lang.t('条记忆', 'memories') }}
            </span>
          </div>
        </section>

        <footer class="dsm-foot">
          <button class="dsm-secondary" @click="onCloseRequested">
            {{ sim.isAwaitingNextDay
                ? lang.t('关闭（保持暂停）', 'Close (stay paused)')
                : lang.t('关闭', 'Close') }}
          </button>
          <button
            v-if="sim.isAwaitingNextDay"
            class="dsm-primary"
            @click="startNextDay"
          >
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

const summary = computed(() => sim.pendingSummary || ({} as any));

function pick(zh?: string, en?: string): string {
  if (lang.lang === 'en') return (en || zh || '').trim();
  return (zh || en || '').trim();
}

const titleText = computed(() => pick(summary.value.title_zh, summary.value.title_en));

const protagonistName = computed(() => {
  const p = summary.value.protagonist;
  if (!p) return '';
  return lang.lang === 'en' ? (p.name_en || p.name || '') : (p.name || p.name_en || '');
});
const protagonistWhy = computed(() => {
  const p = summary.value.protagonist;
  if (!p) return '';
  return pick(p.why_zh, p.why_en);
});

const supportingCast = computed(() => {
  const arr = (summary.value.supporting || []) as Array<any>;
  return arr
    .map(c => ({
      name: lang.lang === 'en' ? (c.name_en || c.name || '') : (c.name || c.name_en || ''),
      role: pick(c.role_zh, c.role_en),
    }))
    .filter(c => !!c.name);
});

const storyText = computed(() => pick(summary.value.story_zh, summary.value.story_en));
const storyParagraphs = computed(() => {
  const t = storyText.value;
  if (!t) return [] as string[];
  return t.split(/\n{2,}/).map(s => s.trim()).filter(Boolean);
});

const tomorrowText = computed(() => pick(summary.value.tomorrow_zh, summary.value.tomorrow_en));
const tomorrowLines = computed(() => {
  const t = tomorrowText.value;
  if (!t) return [] as string[];
  return t
    .split(/\n+/)
    .map(s => s.replace(/^[-*•·\d.、]+\s*/, '').trim())
    .filter(Boolean);
});

const narrativeText = computed(() => {
  const s = sim.pendingSummary;
  if (!s) return '';
  return pick(s.narrative_zh, s.narrative_en);
});

function shortTs(iso?: string): string {
  if (!iso) return '';
  try { return iso.replace('T', ' ').slice(0, 16); } catch { return iso; }
}

async function startNextDay() {
  await sim.startNextDay();
}
function onCloseRequested() {
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
  width: min(820px, 94vw);
  max-height: 90vh;
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
  display: flex; align-items: flex-start; justify-content: space-between; gap: 14px;
}
.dsm-head-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.dsm-badge {
  color: var(--accent-warn);
  font-weight: 700;
  letter-spacing: 0.5px;
  font-size: 11.5px;
  text-transform: uppercase;
}
.dsm-title {
  margin: 0;
  font-size: 19px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
}
.dsm-sub {
  display: flex; flex-wrap: wrap; gap: 6px;
  font-size: 12px; color: var(--text-very-dim);
}
.dsm-day { font-family: Consolas, monospace; color: var(--text-secondary); }
.dsm-when { color: var(--text-very-dim); }
.dsm-warn { color: var(--accent-danger); }
.dsm-close {
  background: none; border: none;
  color: var(--text-very-dim);
  font-size: 22px;
  cursor: pointer;
  padding: 0 8px;
  flex: 0 0 auto;
}
.dsm-close:hover { color: var(--accent-warn); }

.dsm-body {
  padding: 18px 24px;
  overflow-y: auto;
  flex: 1;
  display: flex; flex-direction: column; gap: 16px;
}

.dsm-cast {
  display: flex; flex-wrap: wrap; gap: 18px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--border-soft);
}
.dsm-cast-label {
  display: block;
  font-size: 10.5px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text-very-dim);
  margin-bottom: 6px;
}
.dsm-protagonist { flex: 0 0 auto; max-width: 260px; }
.dsm-proto-card {
  background: linear-gradient(135deg, rgba(255,196,82,0.16), rgba(255,128,82,0.08));
  border: 1px solid rgba(255,196,82,0.35);
  border-radius: 10px;
  padding: 8px 12px;
  display: flex; flex-direction: column; gap: 4px;
}
.dsm-proto-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent-warn, #ffc452);
}
.dsm-proto-why {
  font-size: 11.5px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.dsm-supporting { flex: 1 1 280px; min-width: 240px; }
.dsm-cast-list {
  display: flex; flex-wrap: wrap; gap: 6px 8px;
  list-style: none; padding: 0; margin: 0;
}
.dsm-cast-chip {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  padding: 4px 11px;
  font-size: 12px;
  color: var(--text-secondary);
  display: inline-flex; align-items: center; gap: 4px;
}
.dsm-chip-name { color: var(--text-primary); font-weight: 500; }
.dsm-chip-role { color: var(--text-very-dim); font-size: 11px; }

.dsm-story {
  display: flex; flex-direction: column; gap: 12px;
}
.dsm-para {
  margin: 0;
  color: var(--text-primary);
  font-size: 14.5px;
  line-height: 1.85;
  text-indent: 2em;
}

.dsm-synopsis {
  border-left: 3px solid var(--accent-warn, #ffc452);
  padding: 6px 12px;
  background: rgba(255,196,82,0.05);
  border-radius: 0 6px 6px 0;
}
.dsm-synopsis-label {
  display: block;
  font-size: 10.5px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--accent-warn, #ffc452);
  margin-bottom: 2px;
}
.dsm-synopsis p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.dsm-tomorrow {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 10px 14px;
}
.dsm-tomorrow-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-good-soft, #66BB6A);
  margin-bottom: 6px;
}
.dsm-tomorrow ul {
  margin: 0; padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}
.dsm-tomorrow li + li { margin-top: 2px; }

.dsm-stats {
  display: flex; flex-wrap: wrap; gap: 14px;
  border-top: 1px dashed var(--border-soft);
  padding-top: 12px;
  font-size: 11.5px;
  color: var(--text-very-dim);
}
.dsm-stat b { color: var(--accent-warm-soft); margin-right: 4px; }

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
