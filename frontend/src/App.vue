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
      <span class="brand">SIGSAgent · {{ lang.t('校园多智能体', 'Campus Multi-Agent') }}</span>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { connectWs } from '@/api/ws';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';

const lang = useLangStore();
const events = useEventsStore();

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

onMounted(() => {
  // Sync html lang attribute on first paint.
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang.lang === 'en' ? 'en' : 'zh-CN';
  }
  connectWs();
});
</script>
