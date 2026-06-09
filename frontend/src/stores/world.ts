import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type SceneGraphResponse } from '@/api/endpoints';
import { MOCK_SCENE_GRAPH, MOCK_WORLD } from '@/mock/data';

export const useWorldStore = defineStore('world', () => {
  const sceneGraph = ref<SceneGraphResponse | null>(null);
  const worldSnapshot = ref<any | null>(null);
  const lastTickAt = ref<string | null>(null);
  const usingMock = ref(false);
  // When false, live WS ticks / polling stop driving the snapshot (playback
  // mode takes over via setSnapshot()).
  const liveEnabled = ref(true);
  let pollHandle: number | null = null;

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
    if (!liveEnabled.value) return;  // playback owns the snapshot; don't clobber it
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
    if (!liveEnabled.value) return;  // playback owns the snapshot
    if (!payload) return;
    if (payload.sim_time) lastTickAt.value = String(payload.sim_time);
    if (payload.world) worldSnapshot.value = payload.world;
  }

  /** Directly set the snapshot (used by playback to render a recorded frame).
   *  Bypasses the liveEnabled gate. */
  function setSnapshot(snap: any, simTime?: string) {
    worldSnapshot.value = snap;
    if (simTime) lastTickAt.value = String(simTime);
  }
  function setLive(on: boolean) { liveEnabled.value = on; }

  /** Begin polling /api/world every `intervalMs` ms. Safe to call repeatedly. */
  function startPolling(intervalMs = 3000) {
    if (pollHandle !== null) return;
    pollHandle = window.setInterval(() => { void loadWorld(); }, intervalMs);
  }
  function stopPolling() {
    if (pollHandle !== null) {
      window.clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  return {
    sceneGraph, worldSnapshot, lastTickAt, usingMock, liveEnabled,
    loadScene, loadWorld, applyTick, setSnapshot, setLive,
    startPolling, stopPolling,
  };
});
