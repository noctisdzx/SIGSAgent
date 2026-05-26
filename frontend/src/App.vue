<template>
  <div class="app-shell">
    <nav class="top-nav">
      <span class="brand">SIGSAgent · 校园多智能体</span>
      <router-link class="nav-link" to="/relations">人际关系</router-link>
      <router-link class="nav-link" to="/scene">场景拓扑</router-link>
      <router-link class="nav-link" to="/agent">NPC 详情</router-link>
      <router-link class="nav-link" to="/memory-graph">记忆图谱</router-link>
      <router-link class="nav-link" to="/timeline">时间线</router-link>
    </nav>
    <main class="page">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { connectWs } from '@/api/ws';

onMounted(() => {
  connectWs();
});
</script>
