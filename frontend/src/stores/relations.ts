import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type RelationEdge } from '@/api/endpoints';
import { MOCK_RELATIONS } from '@/mock/data';

/** Normalize {source,target} or {from,to} payloads into a stable {from,to} pair. */
export function edgeFromTo(e: RelationEdge): { from: string; to: string } {
  const from = String(e.from ?? e.source ?? '');
  const to = String(e.to ?? e.target ?? '');
  return { from, to };
}

export const useRelationsStore = defineStore('relations', () => {
  const edges = ref<RelationEdge[]>([]);
  const usingMock = ref(false);

  async function load() {
    try {
      const res = await api.relations();
      edges.value = res?.edges || [];
      if (!edges.value.length) throw new Error('empty relations');
      usingMock.value = false;
    } catch (err) {
      console.warn('[relations] using mock', err);
      edges.value = MOCK_RELATIONS.edges;
      usingMock.value = true;
    }
  }

  return { edges, usingMock, load };
});
