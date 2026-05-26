import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { api } from '@/api/endpoints';

export interface DaySummary {
  day: string;
  ts_real: string;
  ts_sim: string;
  narrative_zh: string;
  narrative_en: string;
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

  function applyDaySummaryEvent(payload: any) {
    if (!payload || !payload.day) return;
    const entry: DaySummary = {
      day: String(payload.day),
      ts_real: String(payload.ts_real || ''),
      ts_sim: String(payload.ts_sim || ''),
      narrative_zh: String(payload.narrative_zh || ''),
      narrative_en: String(payload.narrative_en || ''),
      stats: payload.stats || {},
      degraded: !!payload.degraded,
    };
    // De-dup by day
    const idx = summaries.value.findIndex(s => s.day === entry.day);
    if (idx >= 0) summaries.value.splice(idx, 1, entry);
    else summaries.value.push(entry);
    // Auto-open modal on incoming summary
    pendingSummary.value = entry;
    // Sim should now be paused server-side
    running.value = false;
    pauseReason.value = `day_summary:${entry.day}`;
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
    refreshStatus, loadSummaries,
    applyDaySummaryEvent, dismissSummary, openLatestSummary,
    pause, resume, startNextDay,
    startPolling, stopPolling,
  };
});
