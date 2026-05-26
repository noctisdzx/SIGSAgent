import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '@/api/endpoints';

export const useAgentsStore = defineStore('agents', () => {
  const list = ref<any[]>([]);
  const selectedId = ref<string | null>(null);
  const detail = ref<any | null>(null);
  const memory = ref<any | null>(null);
  const schedule = ref<any | null>(null);
  const history = ref<any[]>([]);

  async function loadList() {
    list.value = await api.agents();
  }
  async function select(id: string) {
    selectedId.value = id;
    [detail.value, memory.value, schedule.value, history.value] = await Promise.all([
      api.agent(id),
      api.agentMemory(id),
      api.agentSchedule(id),
      api.agentHistory(id),
    ]);
  }

  return { list, selectedId, detail, memory, schedule, history, loadList, select };
});
