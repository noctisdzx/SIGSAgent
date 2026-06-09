/**
 * Heat-map store for the scene topology view.
 *
 * Two independent counters accumulate over the lifetime of the page:
 *   - `moveEdgeCounts`  : how many times NPCs traversed each undirected
 *                         scene-graph edge (room A ↔ room B).
 *   - `dwellRoomCounts` : how many `(agent, snapshot)` samples landed in
 *                         each room. A rough proxy for "time spent here"
 *                         that grows as long as agents linger.
 *
 * Both counters are stable across route changes (we keep them in a store
 * rather than view-local state) and persisted to localStorage so a page
 * refresh does not wipe the heat map mid-session. Use `reset()` to clear.
 */
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

const LS_KEY = 'sigs_heat_v1';

interface PersistedHeat {
  moveEdgeCounts: Record<string, number>;
  dwellRoomCounts: Record<string, number>;
  lastTickAt?: string | null;
}

function edgeKey(a: string, b: string): string {
  // Undirected: same edge regardless of traversal direction.
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function safeLoad(): PersistedHeat {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { moveEdgeCounts: {}, dwellRoomCounts: {} };
    const obj = JSON.parse(raw);
    return {
      moveEdgeCounts: obj.moveEdgeCounts || {},
      dwellRoomCounts: obj.dwellRoomCounts || {},
      lastTickAt: obj.lastTickAt || null,
    };
  } catch {
    return { moveEdgeCounts: {}, dwellRoomCounts: {} };
  }
}

export const useHeatStore = defineStore('heat', () => {
  const seeded = safeLoad();
  const moveEdgeCounts = ref<Record<string, number>>(seeded.moveEdgeCounts);
  const dwellRoomCounts = ref<Record<string, number>>(seeded.dwellRoomCounts);
  /** Last sim-tick timestamp we sampled for dwell, used to dedupe samples
   *  when several Vue components subscribe to the same world snapshot. */
  const lastDwellTickAt = ref<string | null>(seeded.lastTickAt || null);

  function persist() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        moveEdgeCounts: moveEdgeCounts.value,
        dwellRoomCounts: dwellRoomCounts.value,
        lastTickAt: lastDwellTickAt.value,
      } as PersistedHeat));
    } catch {
      // localStorage may be full or unavailable — silently skip; the in-memory
      // counters keep working.
    }
  }

  /** Bump the move counter for the edge (from ↔ to). Called per
   *  `behavior.move ok=true` event. No-op when from === to. */
  function recordMove(from: string | null | undefined, to: string | null | undefined) {
    if (!from || !to || from === to) return;
    const k = edgeKey(from, to);
    moveEdgeCounts.value[k] = (moveEdgeCounts.value[k] || 0) + 1;
    persist();
  }

  /** Sample the current world snapshot for dwell heat. Increments each
   *  room's counter by the number of agents currently in it. Dedupes on
   *  `tickAt` so calling this multiple times for the same tick is safe. */
  function sampleDwell(
    tickAt: string | null,
    agents: Array<{ location_uid?: string | null }>,
  ) {
    if (!tickAt) return;
    if (tickAt === lastDwellTickAt.value) return;
    for (const a of agents) {
      const uid = a.location_uid;
      if (!uid) continue;
      dwellRoomCounts.value[uid] = (dwellRoomCounts.value[uid] || 0) + 1;
    }
    lastDwellTickAt.value = tickAt;
    persist();
  }

  function reset() {
    moveEdgeCounts.value = {};
    dwellRoomCounts.value = {};
    lastDwellTickAt.value = null;
    persist();
  }

  /** Replace the local counters with the backend's whole-run cumulative heat
   *  (GET /api/heatmap). Keys already match ("a|b" move edges, room-uid dwell),
   *  so the scene graph renders the aggregate immediately. */
  function loadAggregate(
    moves: Record<string, number> | null | undefined,
    dwell: Record<string, number> | null | undefined,
  ) {
    moveEdgeCounts.value = { ...(moves || {}) };
    dwellRoomCounts.value = { ...(dwell || {}) };
    persist();
  }

  const maxMoveCount = computed(() => {
    let m = 0;
    for (const v of Object.values(moveEdgeCounts.value)) if (v > m) m = v;
    return m;
  });
  const maxDwellCount = computed(() => {
    let m = 0;
    for (const v of Object.values(dwellRoomCounts.value)) if (v > m) m = v;
    return m;
  });

  /** Look up a normalised heat (0..1) for an undirected edge. */
  function moveHeat(from: string, to: string): number {
    if (maxMoveCount.value <= 0) return 0;
    return (moveEdgeCounts.value[edgeKey(from, to)] || 0) / maxMoveCount.value;
  }

  /** Look up a normalised heat (0..1) for a room. */
  function dwellHeat(uid: string): number {
    if (maxDwellCount.value <= 0) return 0;
    return (dwellRoomCounts.value[uid] || 0) / maxDwellCount.value;
  }

  return {
    moveEdgeCounts, dwellRoomCounts, lastDwellTickAt,
    maxMoveCount, maxDwellCount,
    recordMove, sampleDwell, reset, loadAggregate,
    moveHeat, dwellHeat,
  };
});
