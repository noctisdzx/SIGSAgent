import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type SceneEntry } from '@/api/endpoints';
import { MOCK_SCENES } from '@/mock/data';

export const useScenesStore = defineStore('scenes', () => {
  const scenes = ref<SceneEntry[]>([]);
  const usingMock = ref(false);

  async function load() {
    try {
      const res = await api.scenesLibrary();
      scenes.value = res?.scenes || [];
      if (!scenes.value.length) throw new Error('empty scenes');
      usingMock.value = false;
    } catch (err) {
      console.warn('[scenes] using mock', err);
      scenes.value = MOCK_SCENES.scenes;
      usingMock.value = true;
    }
  }

  return { scenes, usingMock, load };
});
