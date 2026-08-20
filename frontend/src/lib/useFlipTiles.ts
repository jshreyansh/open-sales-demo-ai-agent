import { useLayoutEffect, useRef } from "react";

// FLIP (First-Last-Invert-Play) for the participant tiles.
//
// Why this exists: the tiles move between three layouts — one big tile, two
// side by side, and a narrow rail beside the shared screen. Those are
// different grid track COUNTS (1 col, 2 cols, 2 rows), and CSS cannot
// interpolate between different numbers of tracks. Transitioning
// grid-template-* only works while the count is stable, which is why the
// rail flip landed as a hard jump no matter how the transition was tuned.
//
// FLIP sidesteps that entirely: let the browser do the layout change
// instantly, then measure where each tile ACTUALLY ended up, transform it
// back to where it was, and animate that transform away. The layout is never
// animated — only a transform is, which is GPU-cheap and always smooth
// regardless of what changed underneath.
//
// `key` is whatever identifies the current layout; when it changes, the
// positions captured on the previous render are used as the "first" frame.

const DURATION_MS = 520;
const EASING = "cubic-bezier(0.32, 0.72, 0, 1)";

export function useFlipTiles(containerRef: React.RefObject<HTMLElement>, key: string) {
  // Rects from the render BEFORE this one, keyed by each tile's data-flip-id.
  const prev = useRef<Map<string, DOMRect>>(new Map());
  const firstRun = useRef(true);

  useLayoutEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const tiles = Array.from(root.querySelectorAll<HTMLElement>("[data-flip-id]"));

    const next = new Map<string, DOMRect>();
    for (const el of tiles) next.set(el.dataset.flipId!, el.getBoundingClientRect());

    // Nothing to invert against on the very first paint — just record.
    if (firstRun.current) {
      firstRun.current = false;
      prev.current = next;
      return;
    }

    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      for (const el of tiles) {
        const id = el.dataset.flipId!;
        const before = prev.current.get(id);
        const after = next.get(id);
        // A tile that wasn't mounted before (the agent arriving) has no
        // "first" frame — it gets its own entrance animation in CSS instead,
        // and forcing a FLIP on it would fly it in from a meaningless origin.
        if (!before || !after || before.width === 0 || after.width === 0) continue;

        const dx = before.left - after.left;
        const dy = before.top - after.top;
        const sx = before.width / after.width;
        const sy = before.height / after.height;
        // Sub-pixel noise isn't worth animating.
        if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01) {
          continue;
        }

        el.animate(
          [
            { transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
            { transform: "none" },
          ],
          { duration: DURATION_MS, easing: EASING, composite: "replace" },
        );
      }
    }

    prev.current = next;
  }, [containerRef, key]);
}
