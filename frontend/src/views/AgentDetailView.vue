<!--
  Single-NPC detail page.
  Left: scrollable searchable NPC list.
  Right: tabs = 记忆 / 日程 / 行为历史 / 感知.
-->
<template>
  <div class="agent-page">
    <aside class="list">
      <div class="list-head">
        <h3>{{ lang.t('NPC 列表', 'NPC List') }} · {{ filtered.length }}</h3>
        <input
          class="search"
          v-model="q"
          :placeholder="lang.t('搜索…', 'Search…')"
        />
      </div>
      <div class="list-body">
        <div v-if="!filtered.length" class="empty">
          {{ lang.t('没有匹配的 NPC。', 'No matching NPC.') }}
        </div>
        <div
          v-for="a in filtered"
          :key="String(a.id)"
          class="item"
          :class="{ active: agents.selectedId === String(a.id) }"
          @click="selectNpc(String(a.id))"
        >
          <span class="dot" :style="{ background: dotColor(a) }" />
          <div class="meta">
            <div class="name">{{ npcName(a) }}</div>
            <div class="role">{{ npcRole(a) }}</div>
          </div>
        </div>
      </div>
    </aside>

    <section class="detail">
      <div class="detail-head">
        <div v-if="agents.detail">
          <div class="d-name">{{ npcName(agents.detail) }}</div>
          <div class="d-role">{{ npcRole(agents.detail) }}</div>
        </div>
        <div v-else class="d-empty">
          {{ lang.t('请在左侧选择一位 NPC。', 'Select an NPC on the left.') }}
        </div>
      </div>
      <div class="tabs">
        <button v-for="t in tabs" :key="t.key" :class="{ active: tab === t.key }" @click="tab = t.key">
          {{ lang.lang === 'en' ? t.en : t.zh }}
        </button>
      </div>
      <div class="tab-body">
        <MemoryPanel
          v-if="tab === 'memory'"
          :stm="agents.memory?.short_term || []"
          :ltm="agents.memory?.long_term  || []"
        />
        <SchedulePanel
          v-else-if="tab === 'schedule'"
          :slots="agents.schedule?.slots || []"
        />
        <BehaviorHistory
          v-else-if="tab === 'history'"
          :items="agents.history || []"
        />
        <PerceptionPanel
          v-else-if="tab === 'perception'"
          :here="perceptionHere"
          :children="perceptionChildren"
          :siblings="perceptionSiblings"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import MemoryPanel from '@/components/MemoryPanel.vue';
import SchedulePanel from '@/components/SchedulePanel.vue';
import BehaviorHistory from '@/components/BehaviorHistory.vue';
import PerceptionPanel from '@/components/PerceptionPanel.vue';
import { useAgentsStore } from '@/stores/agents';
import { useLangStore } from '@/stores/lang';
import type { AgentLite } from '@/api/endpoints';

const lang = useLangStore();
const agents = useAgentsStore();
const route = useRoute();
const router = useRouter();

type TabKey = 'memory' | 'schedule' | 'history' | 'perception';
const tabs: Array<{ key: TabKey; zh: string; en: string }> = [
  { key: 'memory',     zh: '记忆',     en: 'Memory' },
  { key: 'schedule',   zh: '日程',     en: 'Schedule' },
  { key: 'history',    zh: '行为历史', en: 'Behavior' },
  { key: 'perception', zh: '感知',     en: 'Perception' },
];
const tab = ref<TabKey>('memory');
const q = ref('');

const filtered = computed<AgentLite[]>(() => {
  const term = q.value.trim().toLowerCase();
  if (!term) return agents.list;
  return agents.list.filter(a => {
    const hay = [
      a.name, (a as any).name_en, a.role, (a as any).role_en, String(a.id),
    ].filter(Boolean).join(' ').toLowerCase();
    return hay.includes(term);
  });
});

function selectNpc(id: string) {
  router.push(`/agent/${id}`);
}

function npcName(a: any): string {
  return lang.lang === 'en'
    ? (a.name_en || a.name || a.profile?.name_en || a.profile?.name || String(a.id || ''))
    : (a.name || a.name_en || a.profile?.name || String(a.id || ''));
}
function npcRole(a: any): string {
  return lang.lang === 'en'
    ? (a.role_en || a.role || a.profile?.role_en || '')
    : (a.role || a.role_en || a.profile?.role || '');
}
function dotColor(a: any): string {
  return a.color || a.profile?.color || '#90caf9';
}

const perceptionHere = computed(() => {
  const det = agents.detail;
  if (!det) return '';
  return det.location_uid || det.perception?.here || '';
});
const perceptionChildren = computed(() => agents.detail?.perception?.children || []);
const perceptionSiblings = computed(() => agents.detail?.perception?.siblings || []);

async function loadFromRoute() {
  const id = String(route.params.id || '');
  if (!id) return;
  if (!agents.list.length) await agents.loadList();
  await agents.select(id);
}

onMounted(async () => {
  await agents.loadList();
  if (route.params.id) {
    await loadFromRoute();
  } else if (agents.list.length) {
    // auto-select the first NPC for a friendly default view
    router.replace(`/agent/${agents.list[0].id}`);
  }
});

watch(() => route.params.id, () => loadFromRoute());
</script>

<style scoped>
.agent-page { display: flex; height: 100%; }

.list {
  width: 240px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
}
.list-head {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-soft);
}
.list-head h3 {
  color: var(--accent-primary);
  font-size: 13px;
  margin-bottom: 8px;
}
.search {
  width: 100%;
  padding: 6px 10px;
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-soft);
  outline: none;
  font-size: 12px;
}
.search:focus { border-color: var(--accent-active); }
.list-body { flex: 1; overflow-y: auto; padding: 6px; }

.item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12.5px;
  margin-bottom: 2px;
}
.item:hover { background: var(--bg-elevated); }
.item.active { background: var(--bg-elevated-hover); }
.item .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.item .meta { line-height: 1.2; }
.item .name { color: var(--text-primary); font-weight: 600; }
.item .role { color: var(--text-very-dim); font-size: 11px; }
.empty { color: var(--text-disabled); font-size: 12px; padding: 8px; }

.detail { flex: 1; display: flex; flex-direction: column; }
.detail-head {
  padding: 12px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.d-name { color: var(--accent-primary); font-size: 18px; font-weight: 700; }
.d-role { color: var(--text-very-dim); font-size: 12.5px; }
.d-empty { color: var(--text-disabled); font-size: 13px; }

.tabs {
  display: flex;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-soft);
}
.tabs button {
  flex: 1;
  padding: 10px;
  background: transparent;
  border: none;
  color: var(--text-very-dim);
  cursor: pointer;
  font-size: 12px;
  border-bottom: 2px solid transparent;
}
.tabs button:hover { color: var(--text-muted); }
.tabs button.active { color: var(--accent-primary); border-bottom-color: var(--accent-active); background: var(--bg-panel); }
.tab-body { flex: 1; overflow-y: auto; }
</style>
