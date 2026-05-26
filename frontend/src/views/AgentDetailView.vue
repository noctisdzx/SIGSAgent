<!--
  单 NPC 详情：记忆 / 日程 / 行为历史 / 感知 四 tab。
-->
<template>
  <div class="agent-page">
    <aside class="list">
      <h3>NPC 列表</h3>
      <div v-if="!agents.list.length" class="empty">尚未加载（后端未就绪）</div>
      <div
        v-for="a in agents.list"
        :key="a.id"
        class="item"
        :class="{ active: agents.selectedId === a.id }"
        @click="agents.select(a.id)"
      >
        {{ a.name || a.id }}
      </div>
    </aside>

    <section class="detail">
      <div class="tabs">
        <button v-for="t in tabs" :key="t" :class="{ active: tab === t }" @click="tab = t">
          {{ tabLabels[t] }}
        </button>
      </div>
      <div class="tab-body">
        <MemoryPanel
          v-if="tab === 'memory'"
          :stm="agents.memory?.short_term || []"
          :ltm="agents.memory?.long_term || []"
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
          :here="agents.detail?.location_uid || '—'"
          :children="agents.detail?.perception?.children || []"
          :siblings="agents.detail?.perception?.siblings || []"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import MemoryPanel from '@/components/MemoryPanel.vue';
import SchedulePanel from '@/components/SchedulePanel.vue';
import BehaviorHistory from '@/components/BehaviorHistory.vue';
import PerceptionPanel from '@/components/PerceptionPanel.vue';
import { useAgentsStore } from '@/stores/agents';

const agents = useAgentsStore();
const tabs = ['memory', 'schedule', 'history', 'perception'] as const;
const tabLabels: Record<(typeof tabs)[number], string> = {
  memory: '记忆',
  schedule: '日程',
  history: '行为历史',
  perception: '感知',
};
const tab = ref<(typeof tabs)[number]>('memory');

onMounted(async () => {
  try {
    await agents.loadList();
  } catch {
    /* backend not ready yet */
  }
});
</script>

<style scoped>
.agent-page { display: flex; height: 100%; }
.list {
  width: 220px;
  background: #12182b;
  border-right: 1px solid #1e2a45;
  padding: 12px;
  overflow-y: auto;
}
.list h3 { color: #90caf9; font-size: 13px; margin-bottom: 8px; }
.item {
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #cfd8dc;
}
.item:hover { background: #1a2240; }
.item.active { background: #263259; color: #fff; }
.detail { flex: 1; display: flex; flex-direction: column; }
.tabs {
  display: flex;
  background: #0d1220;
  border-bottom: 1px solid #1e2a45;
}
.tabs button {
  flex: 1;
  padding: 10px;
  background: transparent;
  border: none;
  color: #78909c;
  cursor: pointer;
  font-size: 12px;
  border-bottom: 2px solid transparent;
}
.tabs button.active { color: #90caf9; border-bottom-color: #42a5f5; }
.tab-body { flex: 1; overflow-y: auto; }
.empty { color: #546e7a; font-size: 12px; }
</style>
