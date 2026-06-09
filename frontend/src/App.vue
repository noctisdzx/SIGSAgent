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
      <button
        class="nav-btn sim-btn"
        :disabled="sim.exporting"
        @click="onSaveData"
        :title="lang.t('全量保存本局数据（NPC记忆/行为/世界/汇总热力图/关系），服务器留存并下载到本地', 'Save all run data (memory/behavior/world/heatmap/relations); kept on server and downloaded')"
      >
        <template v-if="sim.exporting">⏳ {{ lang.t('保存中…', 'Saving…') }}</template>
        <template v-else>💾 {{ lang.t('保存数据', 'Save data') }}</template>
      </button>
      <button
        class="nav-btn sim-btn"
        :disabled="sim.importing"
        @click="onLoadData"
        :title="lang.t('从本地存档文件载入：恢复世界/记忆/热力/日总结后暂停，点击「继续」即可接着模拟', 'Load a saved run file: restores world/memory/heat/summaries (paused); press Resume to continue')"
      >
        <template v-if="sim.importing">⏳ {{ lang.t('载入中…', 'Loading…') }}</template>
        <template v-else>📂 {{ lang.t('载入数据', 'Load data') }}</template>
      </button>
      <input
        ref="importInput"
        type="file"
        accept="application/json,.json"
        style="display:none"
        @change="onImportFileChange"
      />
      <button
        class="nav-btn sim-btn sim-btn--danger"
        :disabled="sim.shuttingDown"
        @click="onShutdown"
        :title="lang.t('先自动全量保存，再优雅关闭后端服务（之后需重启服务）', 'Auto-save, then gracefully stop the backend (restart required after)')"
      >⏻ {{ sim.shuttingDown ? lang.t('已停止', 'Stopped') : lang.t('终止服务', 'Stop') }}</button>

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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { connectWs } from '@/api/ws';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';
import { useSimStore } from '@/stores/sim';
import { useWorldStore } from '@/stores/world';
import DaySummaryModal from '@/components/DaySummaryModal.vue';

const lang = useLangStore();
const events = useEventsStore();
const sim = useSimStore();
const world = useWorldStore();

const importInput = ref<HTMLInputElement | null>(null);

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

async function onSaveData() {
  const name = await sim.exportData();
  if (name) {
    window.alert(lang.t(`已保存并开始下载：${name}`, `Saved & downloading: ${name}`));
  } else {
    window.alert(lang.t('保存失败，请查看后端日志。', 'Save failed — check the backend logs.'));
  }
}

function onLoadData() {
  importInput.value?.click();
}

async function onImportFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  // reset so picking the same file again re-triggers change
  input.value = '';
  if (!file) return;
  const ok = window.confirm(lang.t(
    `确定用存档「${file.name}」覆盖当前运行状态吗？将恢复世界/记忆/热力/日总结并暂停模拟。`,
    `Load save "${file.name}" over the current run? This restores world/memory/heat/summaries and pauses the sim.`,
  ));
  if (!ok) return;
  const summary = await sim.importFromFile(file);
  if (summary) {
    // Re-sync the live views to the restored state.
    world.setLive(true);
    await world.loadWorld();
    events.clear();
    window.alert(lang.t(
      `载入成功：${summary.memory_agents} 个NPC记忆、世界时间 ${shortSim(summary.sim_time) || '—'}。已暂停，点击「继续」接着模拟。`,
      `Loaded: ${summary.memory_agents} NPC memories, sim time ${shortSim(summary.sim_time) || '—'}. Paused — press Resume to continue.`,
    ));
  } else {
    window.alert(lang.t(
      '载入失败：请确认选择的是本系统导出的存档 JSON，并查看后端日志。',
      'Load failed — make sure it is a SIGSAgent export JSON; check the backend logs.',
    ));
  }
}

async function onShutdown() {
  const ok = window.confirm(lang.t(
    '确定终止后端服务吗？会先自动全量保存数据，关闭后需要重新启动服务才能继续使用。',
    'Stop the backend service? Data is auto-saved first; you must restart the service to continue.',
  ));
  if (!ok) return;
  await sim.shutdownService();
  window.alert(lang.t('后端服务已停止。需重新启动服务。', 'Backend service stopped. Please restart it.'));
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
