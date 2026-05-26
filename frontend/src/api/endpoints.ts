import { http } from './http';

export interface SceneGraphResponse {
  rooms: Array<{
    uid: string;
    index: number;
    name: string;
    tag: string[];
    adjacent: string[];
    description: string;
    position: number[];
    containment: number;
    furniture: Array<{ name: string; num: number }>;
  }>;
}

export const api = {
  health: () => http.get('/health').then(r => r.data),
  sceneGraph: () => http.get<SceneGraphResponse>('/scene/graph').then(r => r.data),
  world: () => http.get('/world').then(r => r.data),
  agents: () => http.get('/agents').then(r => r.data),
  agent: (id: string) => http.get(`/agents/${id}`).then(r => r.data),
  agentMemory: (id: string) => http.get(`/agents/${id}/memory`).then(r => r.data),
  agentSchedule: (id: string, day?: string) =>
    http.get(`/agents/${id}/schedule`, { params: { day } }).then(r => r.data),
  agentHistory: (id: string, limit = 100) =>
    http.get(`/agents/${id}/history`, { params: { limit } }).then(r => r.data),
  agentPerception: (id: string) => http.get(`/agents/${id}/perception`).then(r => r.data),
  reloadConfig: () => http.post('/config/reload').then(r => r.data),
  simStart: () => http.post('/sim/start').then(r => r.data),
  simPause: () => http.post('/sim/pause').then(r => r.data),
  simStep: () => http.post('/sim/step').then(r => r.data),
};
