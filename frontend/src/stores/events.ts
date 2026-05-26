import { defineStore } from 'pinia';
import { ref } from 'vue';

export type WsStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';

export interface SimEvent {
  type: string;
  ts_sim?: string;
  agent_id?: string;
  payload?: any;
  [k: string]: any;
}

/**
 * WS event stream + connection status.
 * - `stream` is a rolling ring buffer of recent events (oldest pruned).
 * - `connectionStatus` is updated by `src/api/ws.ts`.
 */
export const useEventsStore = defineStore('events', () => {
  const stream = ref<SimEvent[]>([]);
  const max = 500;

  const connectionStatus = ref<WsStatus>('idle');
  const lastError = ref<string | null>(null);
  const lastWelcomeAt = ref<string | null>(null);

  function push(ev: SimEvent) {
    stream.value.push(ev);
    if (stream.value.length > max) stream.value.splice(0, stream.value.length - max);
  }
  function clear() {
    stream.value = [];
  }
  function setStatus(s: WsStatus, err?: string) {
    connectionStatus.value = s;
    if (err !== undefined) lastError.value = err;
  }
  function noteWelcome(ts?: string) {
    lastWelcomeAt.value = ts || new Date().toISOString();
  }

  return {
    stream,
    connectionStatus,
    lastError,
    lastWelcomeAt,
    push,
    clear,
    setStatus,
    noteWelcome,
  };
});
