<!--
  App shell.

  Layout:
  +------------------------------------------------------------+
  | top-nav: brand · routes · spacer · WS indicator · 中/EN btn |
  +------------------------------------------------------------+
  | <router-view/>                                              |
  +------------------------------------------------------------+
-->
<template>
  <div class="app-shell">
    <nav class="top-nav">
      <router-link class="brand" to="/">SIGSAgent · {{ lang.t('校园多智能体', 'Campus Multi-Agent') }}</router-link>

      <router-link class="nav-link" to="/relations">
        {{ lang.t('人际关系', 'Relations') }}
      </router-link>
      <router-link class="nav-link" to="/scene">
        {{ lang.t('场景拓扑', 'Scene Topology') }}
      </router-link>
      <router-link class="nav-link" to="/agent">
        {{ lang.t('NPC 详情', 'NPC Detail') }}
      </router-link>
      <router-link class="nav-link" to="/memory-graph">
        {{ lang.t('记忆图谱', 'Memory Graph') }}
      </router-link>
      <router-link class="nav-link" to="/timeline">
        {{ lang.t('时间线', 'Timeline') }}
      </router-link>

      <span class="spacer" />

      <!-- Sim control cluster -->
      <span class="sim-clock" :title="lang.t('当前游戏时间', 'In-game time')">
        ⏱ {{ shortSim(sim.simTime) || '—' }}
      </span>
      <span class="sim-state" :class="sim.running ? 'on' : 'off'">
        {{ sim.running
          ? lang.t('运行中', 'Running')
          : lang.t('已暂停', 'Paused') }}
      </span>
      <button
        v-if="sim.running"
        class="nav-btn sim-btn"
        @click="sim.pause()"
        :title="lang.t('暂停模拟', 'Pause simulation')"
      >⏸ {{ lang.t('暂停', 'Pause') }}</button>
      <button
        v-else
        class="nav-btn sim-btn sim-btn--primary"
        @click="sim.resume()"
        :title="sim.isAwaitingNextDay
          ? lang.t('开启下一天', 'Start next day')
          : lang.t('继续模拟', 'Resume simulation')"
      >
        ▶ {{ sim.isAwaitingNextDay
          ? lang.t('下一天', 'Next day')
          : lang.t('继续', 'Resume') }}
      </button>
      <button
        class="nav-btn sim-btn"
        :disabled="sim.summarizing"
        @click="sim.summarizeNow()"
        :title="lang.t('用 LLM 立即总结今天发生的事（不暂停模拟）', 'LLM-recap today now (does not pause)')"
      >
        <template v-if="sim.summarizing">⏳ {{ lang.t('总结中…', 'Summarizing…') }}</template>
        <template v-else>✍ {{ lang.t('立即总结', 'Recap now') }}</template>
      </button>
      <button
        v-if="sim.summaries.length"
        class="nav-btn sim-btn"
        @click="sim.openLatestSummary()"
        :title="lang.t('查看最近一天的旁白', 'Open latest day-summary')"
      >📜 {{ lang.t('旁白', 'Recap') }}</button>

      <span class="ws-indicator" :title="wsTitle">
        <span class="ws-dot" :class="events.connectionStatus" />
        {{ wsLabel }}
      </span>
      <button class="nav-btn" @click="lang.toggle()" :title="lang.t('切换语言', 'Toggle language')">
        {{ lang.otherLabel }}
      </button>
    </nav>
    <main class="page">
      <router-view />
    </main>
    <DaySummaryModal />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue';
import { connectWs } from '@/api/ws';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';
import { useSimStore } from '@/stores/sim';
import DaySummaryModal from '@/components/DaySummaryModal.vue';

const lang = useLangStore();
const events = useEventsStore();
const sim = useSimStore();

const wsLabel = computed(() => {
  switch (events.connectionStatus) {
    case 'connected':    return lang.t('已连接', 'Live');
    case 'connecting':   return lang.t('连接中', 'Connecting');
    case 'reconnecting': return lang.t('重连中', 'Reconnecting');
    case 'closed':       return lang.t('已断开', 'Offline');
    default:             return lang.t('未连接', 'Idle');
  }
});
const wsTitle = computed(() => `WebSocket · ${events.connectionStatus}`);

function shortSim(iso?: string): string {
  if (!iso) return '';
  try { return iso.replace('T', ' ').slice(5, 16); } catch { return iso; }
}

onMounted(async () => {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang.lang === 'en' ? 'en' : 'zh-CN';
  }
  connectWs();
  await sim.refreshStatus();
  await sim.loadSummaries();
  sim.startPolling(4000);
});
onBeforeUnmount(() => {
  sim.stopPolling();
});
</script>
