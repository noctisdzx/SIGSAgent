import { http } from './http';

export interface Room {
  uid: string;
  index: number;
  name: string;
  tag: string[];
  adjacent: string[];
  description: string;
  position: number[];
  containment: number;
  furniture: Array<{ name: string; num: number }>;
}

export interface SceneGraphResponse {
  nodes?: any[];
  edges?: any[];
  rooms: Room[];
}

export interface AgentLite {
  id: string | number;
  name: string;
  role?: string;
  location_uid?: string;
  group?: string;
  profile_summary?: string;
  // bilingual variants the backend may include
  name_en?: string;
  role_en?: string;
  group_zh?: string;
  group_en?: string;
  color?: string;
  [k: string]: any;
}

export interface RelationEdge {
  source: string | number;
  target: string | number;
  label: string;
  label_en?: string;
  weight?: number;
  tone?: string;
  color?: string;
  // alt naming from older payloads
  from?: string | number;
  to?: string | number;
  [k: string]: any;
}

export interface SceneEntry {
  id: string | number;
  title: string;
  title_en?: string;
  tags?: string[];
  people?: Array<string | number>;
  trigger?: string;
  trigger_en?: string;
  narrative_zh?: string;
  narrative_en?: string;
  weather?: string;
  space_zh?: string;
  space_en?: string;
  time_band?: string;
  weekday_pattern?: string;
  triplets?: any[];
  outcomes?: string[];
  [k: string]: any;
}

export interface TimelineEvent {
  day?: string;
  time?: string;
  ts?: string;
  title?: string;
  title_en?: string;
  location_uid?: string;
  people?: Array<string | number>;
  narrative_zh?: string;
  narrative_en?: string;
  type?: string;
  [k: string]: any;
}

export const api = {
  health: () => http.get('/health').then(r => r.data),
  sceneGraph: () => http.get<SceneGraphResponse>('/scene/graph').then(r => r.data),
  world: () => http.get('/world').then(r => r.data),
  agents: () => http.get<AgentLite[]>('/agents').then(r => r.data),
  agent: (id: string) => http.get(`/agents/${id}`).then(r => r.data),
  agentMemory: (id: string) => http.get(`/agents/${id}/memory`).then(r => r.data),
  agentSchedule: (id: string, day?: string) =>
    http.get(`/agents/${id}/schedule`, { params: { day } }).then(r => r.data),
  agentHistory: (id: string, limit = 100) =>
    http.get(`/agents/${id}/history`, { params: { limit } }).then(r => r.data),
  agentPerception: (id: string) => http.get(`/agents/${id}/perception`).then(r => r.data),
  relations: () =>
    http.get<{ edges: RelationEdge[] }>('/relations').then(r => r.data),
  scenesLibrary: () =>
    http.get<{ scenes: SceneEntry[] }>('/scenes-library').then(r => r.data),
  timelineSeed: () =>
    http.get<{ events: TimelineEvent[] }>('/timeline-seed').then(r => r.data),
  reloadConfig: () => http.post('/config/reload').then(r => r.data),
  simStart: () => http.post('/sim/start').then(r => r.data),
  simPause: () => http.post('/sim/pause').then(r => r.data),
  simStep: () => http.post('/sim/step').then(r => r.data),
  simStatus: () =>
    http.get<{ running: boolean; sim_time: string; pause_reason?: string | null; current_day: string }>(
      '/sim/status',
    ).then(r => r.data),
  simDaySummaries: (limit = 30) =>
    http.get<{ summaries: any[] }>('/sim/day_summaries', { params: { limit } }).then(r => r.data),
};
