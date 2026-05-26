import { defineStore } from 'pinia';
import { ref } from 'vue';

export interface SimEvent {
  type: string;
  ts_sim: string;
  agent_id?: string;
  payload: any;
}

export const useEventsStore = defineStore('events', () => {
  const stream = ref<SimEvent[]>([]);
  const max = 500;

  function push(ev: SimEvent) {
    stream.value.push(ev);
    if (stream.value.length > max) stream.value.splice(0, stream.value.length - max);
  }
  function clear() {
    stream.value = [];
  }

  return { stream, push, clear };
});
