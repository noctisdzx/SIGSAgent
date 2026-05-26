import { defineStore } from 'pinia';
import { ref, reactive } from 'vue';
import { api, type AgentLite } from '@/api/endpoints';
import {
  MOCK_AGENTS,
  mockAgentDetail,
  mockAgentMemory,
  mockAgentSchedule,
  mockAgentHistory,
  mockAgentPerception,
} from '@/mock/data';

interface AgentDetailCache {
  detail?: any;
  memory?: any;
  schedule?: any;
  history?: any[];
  perception?: any;
}

export const useAgentsStore = defineStore('agents', () => {
  const list = ref<AgentLite[]>([]);
  const selectedId = ref<string | null>(null);
  const detail = ref<any | null>(null);
  const memory = ref<any | null>(null);
  const schedule = ref<any | null>(null);
  const history = ref<any[]>([]);
  const usingMock = ref(false);

  // Cache by agent id so re-clicks are instant.
  const cache = reactive<Record<string, AgentDetailCache>>({});

  async function loadList() {
    try {
      const res = await api.agents();
      list.value = Array.isArray(res) ? res : [];
      if (!list.value.length) throw new Error('empty agent list');
      usingMock.value = false;
    } catch (err) {
      console.warn('[agents] /agents failed, using mock', err);
      list.value = MOCK_AGENTS;
      usingMock.value = true;
    }
  }

  function getCached(id: string): AgentDetailCache {
    return (cache[id] = cache[id] || {});
  }

  async function select(id: string) {
    selectedId.value = id;
    const c = getCached(id);

    detail.value = c.detail ?? null;
    memory.value = c.memory ?? null;
    schedule.value = c.schedule ?? null;
    history.value = c.history ?? [];

    try {
      const [d, m, s, h] = await Promise.all([
        api.agent(id),
        api.agentMemory(id),
        api.agentSchedule(id),
        api.agentHistory(id),
      ]);
      c.detail = d; c.memory = m; c.schedule = s; c.history = h;
      detail.value = d; memory.value = m; schedule.value = s; history.value = h;
      usingMock.value = false;
    } catch (err) {
      console.warn('[agents] detail fetch failed, using mock', err);
      c.detail = mockAgentDetail(id);
      c.memory = mockAgentMemory(id);
      c.schedule = mockAgentSchedule(id);
      c.history = mockAgentHistory(id);
      c.perception = mockAgentPerception(id);
      detail.value = c.detail; memory.value = c.memory;
      schedule.value = c.schedule; history.value = c.history;
      usingMock.value = true;
    }
  }

  /** Light-weight fetch only of the detail (used by RelationView side panel). */
  async function loadDetail(id: string): Promise<any> {
    const c = getCached(id);
    if (c.detail) return c.detail;
    try {
      c.detail = await api.agent(id);
      return c.detail;
    } catch {
      c.detail = mockAgentDetail(id);
      usingMock.value = true;
      return c.detail;
    }
  }

  return {
    list, selectedId, detail, memory, schedule, history, usingMock,
    cache, loadList, select, loadDetail,
  };
});
