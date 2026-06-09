import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { api } from '@/api/endpoints';

export interface DaySummaryCastMember {
  name: string;
  name_en: string;
  role_zh?: string;
  role_en?: string;
}

export interface DaySummaryProtagonist {
  name: string;
  name_en: string;
  why_zh?: string;
  why_en?: string;
}

export interface DaySummary {
  day: string;
  ts_real: string;
  ts_sim: string;
  /** One-paragraph synopsis (always present, for backward-compat). */
  narrative_zh: string;
  narrative_en: string;
  /** Literary chapter title (optional, present when LLM is up). */
  title_zh?: string;
  title_en?: string;
  /** Hero of the day. */
  protagonist?: DaySummaryProtagonist;
  /** Notable supporting characters. */
  supporting?: DaySummaryCastMember[];
  /** Multi-paragraph short story (separated by \n\n). */
  story_zh?: string;
  story_en?: string;
  /** Predictions for the next day (one prediction per line). */
  tomorrow_zh?: string;
  tomorrow_en?: string;
  stats?: Record<string, any>;
  degraded?: boolean;
}

export interface WeekAgentEval {
  id: string;
  name: string;
  name_en?: string;
  role?: string;
  favorite_place?: string;
  evaluation_zh?: string;
  evaluation_en?: string;
  wants?: string[];
  pain_points?: string[];
  degraded?: boolean;
}

export interface WeekSummary {
  week: string;
  week_start: string;
  week_end: string;
  ts_real?: string;
  ts_sim?: string;
  n_agents?: number;
  agents: WeekAgentEval[];
}

export const useSimStore = defineStore('sim', () => {
  const running = ref(true);
  const simTime = ref<string>('');
  const currentDay = ref<string>('');
  const pauseReason = ref<string | null>(null);

  /** Full bilingual narrative log; appended on every day_summary event. */
  const summaries = ref<DaySummary[]>([]);
  /** When non-null, modal is open and showing this summary. */
  const pendingSummary = ref<DaySummary | null>(null);

  /** Weekly per-agent space-evaluation log + active popup. */
  const weekSummaries = ref<WeekSummary[]>([]);
  const pendingWeekSummary = ref<WeekSummary | null>(null);

  let pollHandle: number | null = null;

  const isAwaitingNextDay = computed(
    () => !!pauseReason.value && pauseReason.value.startsWith('day_summary:')
  );

  async function refreshStatus() {
    try {
      const s = await api.simStatus();
      running.value = !!s.running;
      simTime.value = s.sim_time || '';
      currentDay.value = s.current_day || '';
      pauseReason.value = s.pause_reason || null;
    } catch {
      // backend offline; leave fields as-is
    }
  }

  async function loadSummaries() {
    try {
      const r = await api.simDaySummaries(60);
      summaries.value = (r.summaries || []) as DaySummary[];
    } catch {
      // ignore
    }
  }

  /** Per-day flags marking which day-summary events originated from a
   *  *manual* trigger. When set, the WS handler will skip the auto-pause
   *  mirror so the player can keep the sim running. The flag stays sticky
   *  per day to tolerate duplicate WS/REST emissions. */
  const manualDays = ref<Set<string>>(new Set());

  function applyDaySummaryEvent(payload: any) {
    if (!payload || !payload.day) return;
    const entry: DaySummary = {
      day: String(payload.day),
      ts_real: String(payload.ts_real || ''),
      ts_sim: String(payload.ts_sim || ''),
      narrative_zh: String(payload.narrative_zh || ''),
      narrative_en: String(payload.narrative_en || ''),
      title_zh: payload.title_zh ? String(payload.title_zh) : undefined,
      title_en: payload.title_en ? String(payload.title_en) : undefined,
      protagonist: payload.protagonist || undefined,
      supporting: Array.isArray(payload.supporting) ? payload.supporting : undefined,
      story_zh: payload.story_zh ? String(payload.story_zh) : undefined,
      story_en: payload.story_en ? String(payload.story_en) : undefined,
      tomorrow_zh: payload.tomorrow_zh ? String(payload.tomorrow_zh) : undefined,
      tomorrow_en: payload.tomorrow_en ? String(payload.tomorrow_en) : undefined,
      stats: payload.stats || {},
      degraded: !!payload.degraded,
    };
    const idx = summaries.value.findIndex(s => s.day === entry.day);
    if (idx >= 0) summaries.value.splice(idx, 1, entry);
    else summaries.value.push(entry);
    // Daily summaries no longer pause the sim. Just surface the popup; a newer
    // summary simply overwrites whatever was showing (single `pendingSummary`
    // ref → the modal re-renders with the latest entry).
    pendingSummary.value = entry;
  }

  async function loadWeekSummaries() {
    try {
      const r = await api.simWeekSummaries(12);
      weekSummaries.value = (r.summaries || []) as WeekSummary[];
    } catch {
      // ignore
    }
  }

  function applyWeekSummaryEvent(payload: any) {
    if (!payload || !payload.week) return;
    const entry: WeekSummary = {
      week: String(payload.week),
      week_start: String(payload.week_start || ''),
      week_end: String(payload.week_end || ''),
      ts_real: String(payload.ts_real || ''),
      ts_sim: String(payload.ts_sim || ''),
      n_agents: Number(payload.n_agents || 0),
      agents: Array.isArray(payload.agents) ? payload.agents : [],
    };
    const idx = weekSummaries.value.findIndex(s => s.week === entry.week);
    if (idx >= 0) weekSummaries.value.splice(idx, 1, entry);
    else weekSummaries.value.push(entry);
    pendingWeekSummary.value = entry;
  }

  function dismissWeekSummary() { pendingWeekSummary.value = null; }
  function openLatestWeekSummary() {
    if (weekSummaries.value.length) {
      pendingWeekSummary.value = weekSummaries.value[weekSummaries.value.length - 1];
    }
  }

  /** Force a weekly space evaluation for the current week (does not pause). */
  const summarizingWeek = ref(false);
  async function summarizeWeekNow() {
    if (summarizingWeek.value) return;
    summarizingWeek.value = true;
    try {
      const r = await api.simSummarizeWeekNow();
      if (r?.status === 'ok' && r.summary) {
        applyWeekSummaryEvent(r.summary);
      } else if (r?.reason) {
        console.warn('summarize_week_now failed:', r.reason);
      }
    } catch (e) {
      console.warn('summarize_week_now error:', e);
    } finally {
      summarizingWeek.value = false;
    }
  }

  /** Force a recap of the *current* simulated day (does not pause the loop).
   *  Publishes a `day_summary` WS event the modal reacts to. */
  const summarizing = ref(false);
  async function summarizeNow() {
    if (summarizing.value) return;
    summarizing.value = true;
    // Mark the (best-guess) current day as manual *before* calling the API,
    // so the inbound WS event won't fake a pause.
    const guessDay = (currentDay.value || simTime.value.slice(0, 10) || '').trim();
    if (guessDay) manualDays.value.add(guessDay);
    try {
      const r = await api.simSummarizeNow();
      if (r?.status === 'ok') {
        if (r.day) manualDays.value.add(r.day);
        if (r.summary) {
          applyDaySummaryEvent({ ...r.summary, day: r.day });
        }
      } else if (r?.reason) {
        console.warn('summarize_now failed:', r.reason);
      }
    } catch (e) {
      console.warn('summarize_now error:', e);
    } finally {
      summarizing.value = false;
      // Resync against the real server state in case anything drifted.
      void refreshStatus();
    }
  }

  /** Full-run data export: writes a JSON on the server AND triggers a local
   *  download. Returns the server filename (or null on failure). */
  const exporting = ref(false);
  async function exportData(): Promise<string | null> {
    if (exporting.value) return null;
    exporting.value = true;
    try {
      const r = await api.exportData();
      if (r?.status === 'ok' && r.filename) {
        // Trigger a browser download of the same file the server just wrote.
        try {
          const a = document.createElement('a');
          a.href = api.exportDownloadUrl(r.filename);
          a.download = r.filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
        } catch { /* download is best-effort; the server copy still exists */ }
        return r.filename;
      }
      return null;
    } catch (e) {
      console.warn('exportData failed:', e);
      return null;
    } finally {
      exporting.value = false;
    }
  }

  /** Load a previously saved run (interrupt → continue). Reads a local export
   *  JSON file, ships it to the backend which restores world + memory + heat +
   *  day summaries and leaves the loop PAUSED. Returns the restore summary
   *  (or null on failure). */
  const importing = ref(false);
  async function importFromFile(file: File): Promise<Record<string, any> | null> {
    if (importing.value) return null;
    importing.value = true;
    try {
      const text = await file.text();
      let doc: any;
      try {
        doc = JSON.parse(text);
      } catch {
        console.warn('importFromFile: not valid JSON');
        return null;
      }
      if (!doc || doc.kind !== 'sigsagent_export') {
        console.warn('importFromFile: not a SIGSAgent export document');
        return null;
      }
      const r = await api.importData(doc);
      if (r?.status === 'ok') {
        running.value = false;
        pauseReason.value = null;
        if (r.sim_time) simTime.value = String(r.sim_time);
        await refreshStatus();
        await loadSummaries();
        return r;
      }
      return null;
    } catch (e) {
      console.warn('importFromFile failed:', e);
      return null;
    } finally {
      importing.value = false;
    }
  }

  /** Same as importFromFile but restores a server-side export by name. */
  async function importByName(name: string): Promise<Record<string, any> | null> {
    if (importing.value) return null;
    importing.value = true;
    try {
      const r = await api.importByName(name);
      if (r?.status === 'ok') {
        running.value = false;
        pauseReason.value = null;
        if (r.sim_time) simTime.value = String(r.sim_time);
        await refreshStatus();
        await loadSummaries();
        return r;
      }
      return null;
    } catch (e) {
      console.warn('importByName failed:', e);
      return null;
    } finally {
      importing.value = false;
    }
  }

  /** Auto-save + gracefully shut down the backend process. After this the
   *  service must be restarted. Returns true if the request was accepted. */
  const shuttingDown = ref(false);
  async function shutdownService(): Promise<boolean> {
    if (shuttingDown.value) return false;
    shuttingDown.value = true;
    try {
      await api.serviceShutdown();
    } catch {
      // The process often dies before the HTTP response completes — that's
      // expected and still means the shutdown succeeded.
    }
    stopPolling();
    running.value = false;
    pauseReason.value = 'service_stopped';
    return true;
  }

  function dismissSummary() { pendingSummary.value = null; }

  function openLatestSummary() {
    if (summaries.value.length) {
      pendingSummary.value = summaries.value[summaries.value.length - 1];
    }
  }

  async function pause() {
    try {
      await api.simPause();
      running.value = false;
    } catch {}
    await refreshStatus();
  }

  async function startNextDay() {
    try {
      await api.simStart();
      running.value = true;
      pauseReason.value = null;
    } catch {}
    dismissSummary();
    await refreshStatus();
  }
  const resume = startNextDay;

  function startPolling(intervalMs = 4000) {
    if (pollHandle !== null) return;
    pollHandle = window.setInterval(() => { void refreshStatus(); }, intervalMs);
  }
  function stopPolling() {
    if (pollHandle !== null) {
      window.clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  return {
    running, simTime, currentDay, pauseReason,
    summaries, pendingSummary, isAwaitingNextDay,
    weekSummaries, pendingWeekSummary, summarizingWeek,
    summarizing, exporting, importing, shuttingDown,
    refreshStatus, loadSummaries, loadWeekSummaries,
    applyDaySummaryEvent, dismissSummary, openLatestSummary,
    applyWeekSummaryEvent, dismissWeekSummary, openLatestWeekSummary, summarizeWeekNow,
    pause, resume, startNextDay, summarizeNow,
    exportData, importFromFile, importByName, shutdownService,
    startPolling, stopPolling,
  };
});
