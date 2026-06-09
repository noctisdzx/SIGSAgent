/**
 * Shared movement-animation timing, used by BOTH the scene-graph view (which
 * runs the actual NPC glides) and the playback store (which must hold a frame
 * on screen until those glides finish, so playback never "skips" a tick).
 *
 * Keeping the numbers here is the single source of truth: the scene view spends
 * `frameAnimMs(n)` (scaled by playback speed) animating a frame's `n` moves, and
 * playback waits exactly that long before advancing.
 */

export const MOVE_STAGGER_MS = 110;      // gap between consecutive NPC move starts
export const MOVE_STAGGER_MAX_MS = 800;  // cap on how far behind "now" a start may drift
export const DEFAULT_MOVE_ANIM_MS = 2400;

const VIEW_LS_KEY = 'sigs_scene_view_v2';

/** Current glide duration (ms) as tuned in the scene view, read from the same
 *  localStorage key the view persists to so the two stay in sync. */
export function currentMoveAnimMs(): number {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_LS_KEY) || '{}');
    const m = Number(v?.moveAnimMs);
    if (Number.isFinite(m) && m > 0) return m;
  } catch { /* ignore */ }
  return DEFAULT_MOVE_ANIM_MS;
}

/** How long the staggered starts spread a burst of `n` moves over (ms, 1×). */
export function staggerSpanMs(n: number): number {
  if (n <= 1) return 0;
  return Math.min((n - 1) * MOVE_STAGGER_MS, MOVE_STAGGER_MAX_MS);
}

/** Total wall-time (ms, at 1× speed) for a frame's `n` move animations to fully
 *  settle: the stagger window plus one glide. 0 when nothing moves. */
export function frameAnimMs(n: number): number {
  if (n <= 0) return 0;
  return staggerSpanMs(n) + currentMoveAnimMs();
}
