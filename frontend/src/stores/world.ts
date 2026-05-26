import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type SceneGraphResponse } from '@/api/endpoints';
import { MOCK_SCENE_GRAPH, MOCK_WORLD } from '@/mock/data';

export const useWorldStore = defineStore('world', () => {
  const sceneGraph = ref<SceneGraphResponse | null>(null);
  const worldSnapshot = ref<any | null>(null);
  const lastTickAt = ref<string | null>(null);
  const usingMock = ref(false);

  async function loadScene() {
    try {
      sceneGraph.value = await api.sceneGraph();
      usingMock.value = false;
    } catch (err) {
      console.warn('[world] /scene/graph failed, using mock', err);
      sceneGraph.value = MOCK_SCENE_GRAPH as any;
      usingMock.value = true;
    }
  }
  async function loadWorld() {
    try {
      worldSnapshot.value = await api.world();
      usingMock.value = false;
    } catch (err) {
      console.warn('[world] /world failed, using mock', err);
      worldSnapshot.value = MOCK_WORLD;
      usingMock.value = true;
    }
  }
  function applyTick(payload: any) {
    if (!payload) return;
    if (payload.sim_time) lastTickAt.value = String(payload.sim_time);
    if (payload.world) worldSnapshot.value = payload.world;
  }

  return { sceneGraph, worldSnapshot, lastTickAt, usingMock, loadScene, loadWorld, applyTick };
});
