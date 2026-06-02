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

export const useSimStore = defineStore('sim', () => {
  const running = ref(true);
  const simTime = ref<string>('');
  const currentDay = ref<string>('');
  const pauseReason = ref<string | null>(null);

  /** Full bilingual narrative log; appended on every day_summary event. */
  const summaries = ref<DaySummary[]>([]);
  /** When non-null, modal is open and showing this summary. */
  const pendingSummary = ref<DaySummary | null>(null);
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
    pendingSummary.value = entry;
    // Only mirror auto-pause when this is a rollover-driven summary.
    // Manual triggers (flagged in manualDays) leave loop state alone — the
    // periodic /sim/status poll keeps `running` / `pauseReason` truthful.
    if (!manualDays.value.has(entry.day)) {
      running.value = false;
      pauseReason.value = `day_summary:${entry.day}`;
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
    summarizing,
    refreshStatus, loadSummaries,
    applyDaySummaryEvent, dismissSummary, openLatestSummary,
    pause, resume, startNextDay, summarizeNow,
    startPolling, stopPolling,
  };
});
