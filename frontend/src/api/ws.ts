import { useEventsStore } from '@/stores/events';

let socket: WebSocket | null = null;
let reconnectTimer: number | null = null;

export function connectWs(url = `ws://${location.host}/ws`): void {
  if (socket && socket.readyState <= 1) return;

  socket = new WebSocket(url);
  socket.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      useEventsStore().push(ev);
    } catch (err) {
      console.warn('Bad WS payload', e.data, err);
    }
  };
  socket.onclose = () => {
    if (reconnectTimer) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connectWs(url);
    }, 2000);
  };
  socket.onerror = () => {
    socket?.close();
  };
}

export function disconnectWs(): void {
  socket?.close();
  socket = null;
}
