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
  sceneLayout: () =>
    http.get<{ rooms: Record<string, { x: number; y: number }>; map: any; obstacles?: any; roomAreas?: any }>(
      '/scene/layout',
    ).then(r => r.data),
  saveSceneLayout: (body: { rooms: Record<string, { x: number; y: number }>; map: any; obstacles?: any; roomAreas?: any }) =>
    http.put('/scene/layout', body).then(r => r.data),
  world: () => http.get('/world').then(r => r.data),
  agents: () => http.get<AgentLite[]>('/agents').then(r => r.data),
  agent: (id: string) => http.get(`/agents/${id}`).then(r => r.data),
  agentMemory: (id: string) => http.get(`/agents/${id}/memory`).then(r => r.data),
  agentSchedule: (id: string, day?: string, week?: boolean) =>
    http.get(`/agents/${id}/schedule`, { params: { day, week } }).then(r => r.data),
  agentHistory: (id: string, limit = 100) =>
    http.get(`/agents/${id}/history`, { params: { limit } }).then(r => r.data),
  agentPerception: (id: string) => http.get(`/agents/${id}/perception`).then(r => r.data),
  relations: () =>
    http.get<{ edges: RelationEdge[] }>('/relations').then(r => r.data),
  scenesLibrary: () =>
    http.get<{ scenes: SceneEntry[] }>('/scenes-library').then(r => r.data),
  timelineSeed: () =>
    http.get<{ events: TimelineEvent[] }>('/timeline-seed').then(r => r.data),
  recordings: () =>
    http.get<{ recordings: any[]; current: string | null }>('/recordings').then(r => r.data),
  recording: (name: string) =>
    http.get<{ name: string; header: any; frames: any[] }>(
      `/recordings/${encodeURIComponent(name)}`,
    ).then(r => r.data),
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
  simSummarizeNow: () =>
    http.post<{ status: string; day: string; summary?: any; reason?: string }>(
      '/sim/summarize_now',
    ).then(r => r.data),
  simWeekSummaries: (limit = 12) =>
    http.get<{ summaries: any[] }>('/sim/week_summaries', { params: { limit } }).then(r => r.data),
  simSummarizeWeekNow: () =>
    http.post<{ status: string; week: string; summary?: any; reason?: string }>(
      '/sim/summarize_week_now', undefined, { timeout: 180000 },
    ).then(r => r.data),
  heatmap: () =>
    http.get<{ ticks: number; moves: Record<string, number>; dwell: Record<string, number>; max_move: number; max_dwell: number }>(
      '/heatmap',
    ).then(r => r.data),
  exportData: () =>
    http.post<{ status: string; filename: string; size: number; n_agents: number; sim_time?: string }>(
      '/export', undefined, { timeout: 120000 },
    ).then(r => r.data),
  /** Absolute URL to download a saved export as a JSON attachment. */
  exportDownloadUrl: (name: string) =>
    `${http.defaults.baseURL || ''}/exports/${encodeURIComponent(name)}`,
  /** List server-side saved exports (newest first). */
  exports: () =>
    http.get<{ exports: Array<{ name: string; size: number; mtime: number }> }>(
      '/exports',
    ).then(r => r.data),
  /** Restore a run from an uploaded export document (continue simulation). */
  importData: (doc: any) =>
    http.post<{ status: string; running: boolean; [k: string]: any }>(
      '/import', doc, { timeout: 120000 },
    ).then(r => r.data),
  /** Restore a run from a server-side export file by name. */
  importByName: (name: string) =>
    http.post<{ status: string; running: boolean; source?: string; [k: string]: any }>(
      `/import/by-name/${encodeURIComponent(name)}`, undefined, { timeout: 120000 },
    ).then(r => r.data),
  serviceShutdown: () =>
    http.post<{ status: string; export?: string }>('/service/shutdown').then(r => r.data),
  /** Whether an LLM key is currently active (never returns the key itself). */
  llmStatus: () =>
    http.get<{ configured: boolean; model: string | null; base_url: string | null }>(
      '/llm/status',
    ).then(r => r.data),
  /** Set the DeepSeek/OpenAI-compatible key for this run (in-memory only).
   *  With validate=true the backend probes the key and 400s on failure. */
  setLlmKey: (body: { api_key: string; base_url?: string; model?: string; validate?: boolean }) =>
    http.post<{ status: string; configured: boolean; model: string | null; base_url: string | null }>(
      '/llm/key', body, { timeout: 40000 },
    ).then(r => r.data),
};
