import { useRef } from "react";

/**
 * Gives a DOM ref plus a `highlight()` function that briefly adds the
 * `panel--highlighted` class to it — the standard way a registered
 * component responds to the agent's "highlight" action.
 */
export function useHighlight<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);
  function highlight() {
    // In Meeting Mode the viewer can't scroll the shared screen themselves
    // (it's pointer-events: none, like watching a real screen share) — the
    // agent bringing the target into view is what stands in for that.
    ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    ref.current?.classList.add("panel--highlighted");
    setTimeout(() => ref.current?.classList.remove("panel--highlighted"), 1500);
  }
  return { ref, highlight };
}
