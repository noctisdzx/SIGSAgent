import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { api } from '@/api/endpoints';
import { useWorldStore } from '@/stores/world';
import { useEventsStore } from '@/stores/events';

/**
 * Playback of a recorded run. Loading a recording switches the world store off
 * live mode and drives `worldSnapshot` + the events stream frame-by-frame, so
 * the existing scene-graph visualization (sprites, movement, speech bubbles)
 * replays exactly as it happened.
 */
export const usePlaybackStore = defineStore('playback', () => {
  const active = ref(false);
  const loading = ref(false);
  const name = ref<string | null>(null);
  const frames = ref<any[]>([]);
  const index = ref(0);
  const playing = ref(false);
  const speed = ref(1);            // 1× = one frame per BASE_MS
  const recordings = ref<any[]>([]);

  const BASE_MS = 900;
  let timer: number | null = null;

  const total = computed(() => frames.value.length);
  const current = computed(() => frames.value[index.value] || null);
  const simTime = computed(() => current.value?.sim_time || '');

  async function refreshList() {
    try {
      const data = await api.recordings();
      recordings.value = data.recordings || [];
    } catch (err) {
      console.warn('[playback] list failed', err);
      recordings.value = [];
    }
  }

  async function load(recName: string) {
    loading.value = true;
    pause();
    try {
      const data = await api.recording(recName);
      frames.value = data.frames || [];
      name.value = recName;
      index.value = 0;
      active.value = true;
      const world = useWorldStore();
      world.setLive(false);          // stop live ticks from fighting playback
      useEventsStore().clear();
      applyFrame(0, /*withEvents=*/false);
    } catch (err) {
      console.warn('[playback] load failed', err);
    } finally {
      loading.value = false;
    }
  }

  function applyFrame(i: number, withEvents = true) {
    const f = frames.value[i];
    if (!f) return;
    const world = useWorldStore();
    world.setSnapshot(f.world, f.sim_time);
    if (withEvents) {
      const events = useEventsStore();
      for (const ev of (f.events || [])) events.push(ev);
    }
  }

  function step(delta: number) {
    const next = Math.max(0, Math.min(total.value - 1, index.value + delta));
    seek(next);
  }

  function seek(i: number) {
    index.value = Math.max(0, Math.min(total.value - 1, i));
    // Seeking shows the frame's world but replays its events too so a paused
    // scrub still surfaces that tick's dialog bubbles.
    applyFrame(index.value, true);
  }

  function tick() {
    if (index.value >= total.value - 1) { pause(); return; }
    index.value += 1;
    applyFrame(index.value, true);
  }

  function play() {
    if (!active.value || playing.value) return;
    if (index.value >= total.value - 1) index.value = 0;
    playing.value = true;
    schedule();
  }
  function schedule() {
    if (timer !== null) window.clearTimeout(timer);
    if (!playing.value) return;
    timer = window.setTimeout(() => {
      tick();
      schedule();
    }, BASE_MS / Math.max(0.1, speed.value));
  }
  function pause() {
    playing.value = false;
    if (timer !== null) { window.clearTimeout(timer); timer = null; }
  }
  function setSpeed(s: number) {
    speed.value = s;
    if (playing.value) schedule();
  }

  /** Leave playback and hand the world back to the live feed. */
  function exit() {
    pause();
    active.value = false;
    name.value = null;
    frames.value = [];
    index.value = 0;
    const world = useWorldStore();
    world.setLive(true);
    void world.loadWorld();
  }

  return {
    active, loading, name, frames, index, playing, speed, recordings,
    total, current, simTime,
    refreshList, load, applyFrame, step, seek, play, pause, setSpeed, exit,
  };
});
