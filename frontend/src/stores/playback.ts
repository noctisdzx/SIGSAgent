import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { api } from '@/api/endpoints';
import { useWorldStore } from '@/stores/world';
import { useEventsStore } from '@/stores/events';
import { useSimStore } from '@/stores/sim';
import { frameAnimMs } from '@/anim';

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
  // Default to a gentle 0.5× so NPC movement reads clearly out of the box;
  // users can go even slower (0.25×) or speed up from the controls.
  const speed = ref(0.5);          // 1× = one frame per BASE_MS
  const recordings = ref<any[]>([]);

  // Number of NPC move animations currently in flight on the scene view
  // (pending staggered start OR actively gliding). The scene view reports this;
  // the player waits for it to fall to 0 before advancing, so a frame is held
  // exactly until its glides finish — no time-estimate mismatch, no frame skip.
  const animBusy = ref(0);
  function reportAnimBusy(n: number) { animBusy.value = n; }

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
      // Playback takes EXCLUSIVE ownership of the view: pause the live backend
      // sim so it stops ticking / emitting / recording, and stop the status
      // poll so nothing races the recorded frames until the user exits.
      const sim = useSimStore();
      sim.stopPolling();
      await sim.pause();             // best-effort backend pause
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

  /** Number of NPC moves a frame animates — mirrors the scene view's detection
   *  (successful `move` with a changed location) so the dwell below matches the
   *  glides the view actually plays. */
  function moveCount(i: number): number {
    const f = frames.value[i];
    if (!f?.events) return 0;
    let n = 0;
    for (const ev of f.events) {
      if (ev?.type !== 'behavior') continue;
      const p = ev.payload || {};
      if (p.action_id !== 'move' || !p.ok) continue;
      const from = p.pre_state?.['agent.location_uid'];
      const to = p.post_state?.['agent.location_uid'];
      if (from && to && from !== to) n++;
    }
    return n;
  }

  /** How long to hold the just-applied frame (`i`) on screen before advancing:
   *  long enough for that frame's NPC glides (stagger + one move) to finish, so
   *  playback never skips a tick. Scaled by speed exactly like the glides. */
  function frameDwellMs(i: number): number {
    const sf = Math.max(0.1, speed.value);
    const anim = frameAnimMs(moveCount(i));   // 0 when nothing moves
    return Math.max(BASE_MS, anim) / sf;
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
    const sf = Math.max(0.1, speed.value);
    // Minimum on-screen time per frame so quiet (no-move) frames still read at a
    // steady pace instead of flickering past.
    const minHold = BASE_MS / sf;
    // Safety cap: never wait longer than ~2.5× the estimated dwell for glides to
    // settle, so a stuck/never-ending animation can't stall playback forever.
    const maxHold = Math.max(minHold, frameDwellMs(index.value) * 2.5);
    const startedAt = performance.now();
    // Poll-wait: advance once the frame has shown for `minHold` AND every NPC
    // glide it kicked off has finished (animBusy === 0) — or the safety cap
    // elapsed. Driving advancement off the real animation-settle signal, rather
    // than a fixed time estimate, is what removes the residual frame-skip: we
    // never cut a glide short, even when A* paths are long or starts are
    // staggered across many NPCs.
    const waitStep = () => {
      if (!playing.value) { timer = null; return; }
      const elapsed = performance.now() - startedAt;
      const settled = animBusy.value === 0;
      if (elapsed >= minHold && (settled || elapsed >= maxHold)) {
        tick();
        schedule();
      } else {
        timer = window.setTimeout(waitStep, 30);
      }
    };
    timer = window.setTimeout(waitStep, 30);
  }
  function pause() {
    playing.value = false;
    if (timer !== null) { window.clearTimeout(timer); timer = null; }
  }
  function setSpeed(s: number) {
    speed.value = s;
    if (playing.value) schedule();
  }

  /** Leave playback and hand the world back to the live feed. The backend sim
   *  stays PAUSED (we don't surprise-restart it) — the operator resumes via the
   *  ▶ button; we just re-arm the live status poll + world snapshot. */
  function exit() {
    pause();
    active.value = false;
    name.value = null;
    frames.value = [];
    index.value = 0;
    const world = useWorldStore();
    world.setLive(true);
    void world.loadWorld();
    const sim = useSimStore();
    void sim.refreshStatus();
    sim.startPolling();
  }

  return {
    active, loading, name, frames, index, playing, speed, recordings,
    animBusy, total, current, simTime,
    refreshList, load, applyFrame, step, seek, play, pause, setSpeed, exit,
    reportAnimBusy,
  };
});
