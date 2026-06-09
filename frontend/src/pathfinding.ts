/**
 * Grid-based A* pathfinding for the scene-topology canvas.
 *
 * The campus floor is modelled as an infinite occupancy grid anchored at world
 * origin (0,0). Each cell is `cell` world-units square; a cell is "blocked"
 * (non-walkable) when its `"cx,cy"` key is present in `ObstacleGrid.blocked`.
 * Users paint these cells with the brush tool; NPCs route around them.
 *
 * Why A*: it is the standard, efficient choice for grid pathfinding with static
 * obstacles — optimal paths under an admissible heuristic (octile distance),
 * far fewer expansions than Dijkstra, and trivially supports the 8-direction
 * movement + corner-cutting guard we want for natural diagonal motion.
 */

export interface Pt {
  x: number;
  y: number;
}

export interface ObstacleGrid {
  /** Cell size in world units. */
  cell: number;
  /** Set of blocked cell keys, `"cx,cy"`. */
  blocked: Set<string>;
}

export function cellKey(cx: number, cy: number): string {
  return `${cx},${cy}`;
}

export function worldToCell(x: number, y: number, cell: number): [number, number] {
  return [Math.floor(x / cell), Math.floor(y / cell)];
}

export function cellCenter(cx: number, cy: number, cell: number): Pt {
  return { x: (cx + 0.5) * cell, y: (cy + 0.5) * cell };
}

/** Minimal binary min-heap keyed by a numeric priority. */
class MinHeap<T> {
  private items: T[] = [];
  private prio: number[] = [];
  get size(): number {
    return this.items.length;
  }
  push(item: T, priority: number): void {
    this.items.push(item);
    this.prio.push(priority);
    let i = this.items.length - 1;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.prio[parent] <= this.prio[i]) break;
      this.swap(i, parent);
      i = parent;
    }
  }
  pop(): T | undefined {
    const n = this.items.length;
    if (n === 0) return undefined;
    const top = this.items[0];
    const lastItem = this.items.pop()!;
    const lastPrio = this.prio.pop()!;
    if (n > 1) {
      this.items[0] = lastItem;
      this.prio[0] = lastPrio;
      let i = 0;
      // sift-down
      for (;;) {
        const l = 2 * i + 1;
        const r = 2 * i + 2;
        let smallest = i;
        if (l < this.items.length && this.prio[l] < this.prio[smallest]) smallest = l;
        if (r < this.items.length && this.prio[r] < this.prio[smallest]) smallest = r;
        if (smallest === i) break;
        this.swap(i, smallest);
        i = smallest;
      }
    }
    return top;
  }
  private swap(a: number, b: number): void {
    [this.items[a], this.items[b]] = [this.items[b], this.items[a]];
    [this.prio[a], this.prio[b]] = [this.prio[b], this.prio[a]];
  }
}

const SQRT2 = Math.SQRT2;
// 8-connected neighbour offsets (orthogonal first, then diagonals).
const NEIGHBORS: Array<[number, number, number]> = [
  [1, 0, 1],
  [-1, 0, 1],
  [0, 1, 1],
  [0, -1, 1],
  [1, 1, SQRT2],
  [1, -1, SQRT2],
  [-1, 1, SQRT2],
  [-1, -1, SQRT2],
];

export interface FindPathOptions {
  /** Extra cells of search padding around the start↔goal bounding box. */
  margin?: number;
  /** Hard cap on expanded cells before bailing out (returns null). */
  maxVisited?: number;
}

/**
 * A* between two world points over the occupancy grid.
 *
 * Returns a list of world-space waypoints (including the exact `from` and `to`
 * endpoints) routed around blocked cells, already simplified via line-of-sight
 * so the polyline is short and natural. Returns `null` when no obstacles lie
 * between the points (caller should walk a straight line) or when the search
 * is infeasible (caller falls back to a straight line).
 */
export function findPath(
  grid: ObstacleGrid,
  from: Pt,
  to: Pt,
  opts: FindPathOptions = {},
): Pt[] | null {
  const { cell, blocked } = grid;
  if (blocked.size === 0) return null;

  const [sx, sy] = worldToCell(from.x, from.y, cell);
  const [gx, gy] = worldToCell(to.x, to.y, cell);
  if (sx === gx && sy === gy) return null;

  // If the straight segment is already clear, skip the search entirely.
  if (segmentClear(grid, from, to)) return null;

  const margin = opts.margin ?? 28;
  const maxVisited = opts.maxVisited ?? 60000;
  const minX = Math.min(sx, gx) - margin;
  const maxX = Math.max(sx, gx) + margin;
  const minY = Math.min(sy, gy) - margin;
  const maxY = Math.max(sy, gy) + margin;

  const isBlocked = (cx: number, cy: number): boolean => {
    // Start and goal cells are always walkable so a brush stroke over a room
    // never traps an NPC at its own destination.
    if ((cx === sx && cy === sy) || (cx === gx && cy === gy)) return false;
    return blocked.has(cellKey(cx, cy));
  };

  const h = (cx: number, cy: number): number => {
    const dx = Math.abs(cx - gx);
    const dy = Math.abs(cy - gy);
    // Octile distance.
    return (dx + dy) + (SQRT2 - 2) * Math.min(dx, dy);
  };

  const gScore = new Map<string, number>();
  const cameFrom = new Map<string, string>();
  const open = new MinHeap<[number, number]>();
  const startKey = cellKey(sx, sy);
  gScore.set(startKey, 0);
  open.push([sx, sy], h(sx, sy));

  let visited = 0;
  let found = false;
  while (open.size > 0) {
    const cur = open.pop()!;
    const [cx, cy] = cur;
    const curKey = cellKey(cx, cy);
    if (cx === gx && cy === gy) {
      found = true;
      break;
    }
    if (++visited > maxVisited) return null;
    const curG = gScore.get(curKey)!;
    for (const [dx, dy, cost] of NEIGHBORS) {
      const nx = cx + dx;
      const ny = cy + dy;
      if (nx < minX || nx > maxX || ny < minY || ny > maxY) continue;
      if (isBlocked(nx, ny)) continue;
      // Prevent cutting through the corner between two blocked orthogonals.
      if (dx !== 0 && dy !== 0) {
        if (isBlocked(cx + dx, cy) && isBlocked(cx, cy + dy)) continue;
      }
      const nKey = cellKey(nx, ny);
      const tentative = curG + cost;
      if (tentative < (gScore.get(nKey) ?? Infinity)) {
        cameFrom.set(nKey, curKey);
        gScore.set(nKey, tentative);
        open.push([nx, ny], tentative + h(nx, ny));
      }
    }
  }
  if (!found) return null;

  // Reconstruct cell path goal → start, then reverse.
  const cellsRev: Array<[number, number]> = [];
  let k: string | undefined = cellKey(gx, gy);
  while (k) {
    const [cxs, cys] = k.split(',');
    cellsRev.push([Number(cxs), Number(cys)]);
    k = cameFrom.get(k);
  }
  cellsRev.reverse();

  // World waypoints: exact start, cell centers, exact goal.
  const raw: Pt[] = [from];
  for (let i = 1; i < cellsRev.length - 1; i++) {
    raw.push(cellCenter(cellsRev[i][0], cellsRev[i][1], cell));
  }
  raw.push(to);

  return simplifyPath(grid, raw);
}

/** Greedy line-of-sight string-pulling: keep only waypoints required to avoid
 *  blocked cells, yielding a short polyline instead of a staircase. */
export function simplifyPath(grid: ObstacleGrid, pts: Pt[]): Pt[] {
  if (pts.length <= 2) return pts;
  const out: Pt[] = [pts[0]];
  let anchor = 0;
  for (let i = 2; i < pts.length; i++) {
    if (!segmentClear(grid, pts[anchor], pts[i])) {
      out.push(pts[i - 1]);
      anchor = i - 1;
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}

/** True when the straight segment a→b crosses no blocked cell. Sampled at
 *  half-cell resolution (the brush is much larger than a cell, so this never
 *  tunnels through a real wall). */
export function segmentClear(grid: ObstacleGrid, a: Pt, b: Pt): boolean {
  const { cell, blocked } = grid;
  if (blocked.size === 0) return true;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.hypot(dx, dy);
  const steps = Math.max(1, Math.ceil(dist / (cell * 0.5)));
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = a.x + dx * t;
    const y = a.y + dy * t;
    const [cx, cy] = worldToCell(x, y, cell);
    if (blocked.has(cellKey(cx, cy))) return false;
  }
  return true;
}

/** Sample a point at arc-length fraction `t` (0..1) along a polyline, using the
 *  precomputed cumulative segment lengths. */
export function pointAlong(path: Pt[], cum: number[], total: number, t: number): Pt {
  if (path.length === 1 || total <= 0) return path[0];
  if (t <= 0) return path[0];
  if (t >= 1) return path[path.length - 1];
  const target = t * total;
  // Find the segment containing `target`.
  let lo = 0;
  let hi = cum.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cum[mid] < target) lo = mid + 1;
    else hi = mid;
  }
  const seg = Math.max(1, lo);
  const segStart = cum[seg - 1];
  const segLen = cum[seg] - segStart || 1;
  const f = (target - segStart) / segLen;
  const p0 = path[seg - 1];
  const p1 = path[seg];
  return { x: p0.x + (p1.x - p0.x) * f, y: p0.y + (p1.y - p0.y) * f };
}

/** Cumulative segment lengths for `pointAlong`; returns `{ cum, total }`. */
export function cumulativeLengths(path: Pt[]): { cum: number[]; total: number } {
  const cum = [0];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    total += Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);
    cum.push(total);
  }
  return { cum, total };
}
