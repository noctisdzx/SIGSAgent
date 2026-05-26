import { useEventsStore } from '@/stores/events';
import { useWorldStore } from '@/stores/world';

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;
let attempt = 0;
let manuallyClosed = false;
let activeUrl: string | null = null;

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 15000;

function nextBackoff(): number {
  // exponential backoff with cap
  const ms = Math.min(MAX_BACKOFF_MS, MIN_BACKOFF_MS * 2 ** Math.min(attempt, 6));
  attempt += 1;
  return ms;
}

function defaultUrl(): string {
  if (typeof location === 'undefined') return 'ws://127.0.0.1:5173/ws';
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws`;
}

function handleEvent(raw: any): void {
  const events = useEventsStore();
  const world = useWorldStore();
  if (!raw || typeof raw !== 'object') return;
  const ev = raw as { type?: string; payload?: any; ts_sim?: string; agent_id?: string };

  events.push({
    type: ev.type || 'unknown',
    ts_sim: ev.ts_sim,
    agent_id: ev.agent_id,
    payload: ev.payload,
  });

  switch (ev.type) {
    case 'welcome':
      events.noteWelcome(ev.ts_sim);
      if (ev.payload?.world) world.applyTick({ world: ev.payload.world, sim_time: ev.payload.sim_time });
      break;
    case 'tick':
      world.applyTick(ev.payload || ev);
      break;
    default:
      break;
  }
}

export function connectWs(url?: string): void {
  const target = url || activeUrl || defaultUrl();
  activeUrl = target;
  manuallyClosed = false;

  if (socket && socket.readyState <= WebSocket.OPEN) return;

  const events = useEventsStore();
  events.setStatus(attempt > 0 ? 'reconnecting' : 'connecting');

  try {
    socket = new WebSocket(target);
  } catch (err) {
    console.warn('[ws] open threw', err);
    events.setStatus('closed', String(err));
    scheduleReconnect();
    return;
  }

  socket.onopen = () => {
    attempt = 0;
    events.setStatus('connected');
  };
  socket.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleEvent(data);
    } catch (err) {
      console.warn('[ws] bad payload', e.data, err);
    }
  };
  socket.onerror = () => {
    events.setStatus('reconnecting', 'WebSocket error');
  };
  socket.onclose = () => {
    socket = null;
    if (manuallyClosed) {
      events.setStatus('closed');
      return;
    }
    events.setStatus('reconnecting');
    scheduleReconnect();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimer != null) return;
  const delay = nextBackoff();
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, delay);
}

export function disconnectWs(): void {
  manuallyClosed = true;
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  socket?.close();
  socket = null;
  useEventsStore().setStatus('closed');
}
