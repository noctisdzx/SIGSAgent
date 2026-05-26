import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api, type TimelineEvent } from '@/api/endpoints';
import { MOCK_TIMELINE } from '@/mock/data';

export const useTimelineStore = defineStore('timeline', () => {
  const seedEvents = ref<TimelineEvent[]>([]);
  const usingMock = ref(false);

  async function loadSeed() {
    try {
      const res = await api.timelineSeed();
      seedEvents.value = res?.events || [];
      if (!seedEvents.value.length) throw new Error('empty timeline');
      usingMock.value = false;
    } catch (err) {
      console.warn('[timeline] using mock', err);
      seedEvents.value = MOCK_TIMELINE.events;
      usingMock.value = true;
    }
  }

  return { seedEvents, usingMock, loadSeed };
});
