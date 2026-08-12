import { useRef } from "react";

/**
 * Two visual cues a registered component can use to show the visitor where
 * the agent just acted — the closest practical equivalent to watching a
 * real presenter's cursor land on something, without needing a coordinate/
 * rect system for every actionable element (see uiRegistry.ts's ActionMap,
 * which is just bare closures — no DOM position attached to an action at
 * all). Both are pure CSS anchored to the element's own box (no
 * getBoundingClientRect() math), so they're unaffected by the shared
 * screen's zoom/scroll.
 *
 * Exported as raw element-level functions (not just via the useHighlight
 * hook below) so components with a dynamic set of possible targets — e.g.
 * ContentStudio's 30 format cards, looked up by slug from a ref map rather
 * than a fixed hook instance per target — can call them directly too.
 */
export function scrollToTarget(el: HTMLElement | null) {
  // In Meeting Mode the viewer can't scroll the shared screen themselves
  // (it's pointer-events: none, like watching a real screen share) — the
  // agent bringing the target into view is what stands in for that.
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function applySpotlight(el: HTMLElement | null) {
  scrollToTarget(el);
  el?.classList.add("panel--spotlight");
  setTimeout(() => el?.classList.remove("panel--spotlight"), 1500);
}

export function applyPulse(el: HTMLElement | null) {
  scrollToTarget(el);
  if (!el) return;
  // Restart the animation on repeated pulses (e.g. rapid re-selection) by
  // removing and re-adding the class, since a class that's already present
  // won't re-trigger its CSS animation.
  el.classList.remove("panel--pulse");
  void el.offsetWidth; // force reflow so the removal is committed first
  el.classList.add("panel--pulse");
  setTimeout(() => el.classList.remove("panel--pulse"), 700);
}

/**
 * Gives a DOM ref plus spotlight()/pulse() already bound to it — the
 * standard shape for a component with a fixed, known set of highlight/
 * pulse targets (one hook instance per target, same pattern as the
 * pre-existing Dashboard insights/activeCampaigns usage).
 */
export function useHighlight<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);
  return {
    ref,
    spotlight: () => applySpotlight(ref.current),
    pulse: () => applyPulse(ref.current),
  };
}
