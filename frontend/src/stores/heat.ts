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
  cellCounts?: Record<string, number>;
  agentCellCounts?: Record<string, Record<string, number>>;
  maxCell?: number;
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
      cellCounts: obj.cellCounts || {},
      agentCellCounts: obj.agentCellCounts || {},
      maxCell: obj.maxCell || 0,
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
  /** Per grid-cell traversal counts ("cx,cy" → times an agent entered the
   *  cell). Each agent increments a cell only on *entry* (see the view's
   *  per-frame tracker), so standing still never re-counts — this is the
   *  "trajectory" heat distinct from room-level dwell. */
  const cellCounts = ref<Record<string, number>>(seeded.cellCounts || {});
  /** Same trajectory counts, but split per agent id, so the view can isolate a
   *  single NPC's path ("cx,cy" → entries). */
  const agentCellCounts = ref<Record<string, Record<string, number>>>(seeded.agentCellCounts || {});
  const maxCellCount = ref<number>(seeded.maxCell || 0);
  /** Last sim-tick timestamp we sampled for dwell, used to dedupe samples
   *  when several Vue components subscribe to the same world snapshot. */
  const lastDwellTickAt = ref<string | null>(seeded.lastTickAt || null);

  function persist() {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({
        moveEdgeCounts: moveEdgeCounts.value,
        dwellRoomCounts: dwellRoomCounts.value,
        cellCounts: cellCounts.value,
        agentCellCounts: agentCellCounts.value,
        maxCell: maxCellCount.value,
        lastTickAt: lastDwellTickAt.value,
      } as PersistedHeat));
    } catch {
      // localStorage may be full or unavailable — silently skip; the in-memory
      // counters keep working.
    }
  }

  // Cell counts can fire many times per second during glides; persist them on a
  // throttle so we don't stringify the whole map every frame.
  let cellPersistTimer: number | null = null;
  function persistCellsThrottled() {
    if (cellPersistTimer != null) return;
    cellPersistTimer = window.setTimeout(() => { cellPersistTimer = null; persist(); }, 1500);
  }

  /** Count one agent ENTERING a grid cell. Idempotent per stay: the view only
   *  calls this when an agent's cell actually changes, so a lingering agent
   *  never inflates the count (avoids the dwell over-accumulation problem).
   *  Tracks both the global aggregate and a per-agent breakdown. */
  function recordCellEnter(key: string, agentId?: string) {
    const v = (cellCounts.value[key] || 0) + 1;
    cellCounts.value[key] = v;
    if (v > maxCellCount.value) maxCellCount.value = v;
    if (agentId) {
      let m = agentCellCounts.value[agentId];
      if (!m) { m = {}; agentCellCounts.value[agentId] = m; }
      m[key] = (m[key] || 0) + 1;
    }
    persistCellsThrottled();
  }

  /** Normalised (0..1) trajectory heat for a grid cell. */
  function cellHeat(key: string): number {
    if (maxCellCount.value <= 0) return 0;
    return (cellCounts.value[key] || 0) / maxCellCount.value;
  }

  /** Per-agent trajectory counts (empty when the agent hasn't moved yet). */
  function cellCountsForAgent(agentId: string): Record<string, number> {
    return agentCellCounts.value[agentId] || {};
  }
  /** Max cell count for one agent (for normalising that agent's heat). */
  function maxCellForAgent(agentId: string): number {
    const c = agentCellCounts.value[agentId];
    if (!c) return 0;
    let m = 0;
    for (const k in c) if (c[k] > m) m = c[k];
    return m;
  }

  /** Clear ONLY the grid-cell trajectory heat (aggregate + per-agent), leaving
   *  the move-edge and room-dwell layers intact. */
  function clearCells() {
    cellCounts.value = {};
    agentCellCounts.value = {};
    maxCellCount.value = 0;
    persist();
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
    cellCounts.value = {};
    agentCellCounts.value = {};
    maxCellCount.value = 0;
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
    moveEdgeCounts, dwellRoomCounts, cellCounts, agentCellCounts, lastDwellTickAt,
    maxMoveCount, maxDwellCount, maxCellCount,
    recordMove, sampleDwell, recordCellEnter, reset, clearCells, loadAggregate,
    moveHeat, dwellHeat, cellHeat, cellCountsForAgent, maxCellForAgent,
  };
});
