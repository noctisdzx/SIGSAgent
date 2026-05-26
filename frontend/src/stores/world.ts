import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type SceneGraphResponse } from '@/api/endpoints';

export const useWorldStore = defineStore('world', () => {
  const sceneGraph = ref<SceneGraphResponse | null>(null);
  const worldSnapshot = ref<any | null>(null);

  async function loadScene() {
    sceneGraph.value = await api.sceneGraph();
  }
  async function loadWorld() {
    worldSnapshot.value = await api.world();
  }

  return { sceneGraph, worldSnapshot, loadScene, loadWorld };
});
