import { scrollToTarget } from "./useHighlight";
import clickSoundUrl from "../assets/click.mp3";

/**
 * The single funnel every incoming voice action is meant to pass through
 * (see useProductPages.tsx's handleAgentAction) instead of a component
 * hand-wiring its own ref + useHighlight() instance + fallback check. A
 * target element just needs `data-hl="component:method"` in its JSX --
 * matching backend/src/agent/registry.py's own ids verbatim -- and an
 * always-mounted proxy (a tab button, a StepBar step pill) can opt in as a
 * stand-in via `data-hl-group="<key>"` for whenever the real target isn't
 * rendered yet (wrong tab, wrong wizard step). This replaces three
 * separately hand-rolled versions of that same "pulse the real thing, or
 * fall back to a proxy" check (ContentStudio's inline if/else,
 * MagicReelStudio's pulseInPlaceOrStep, MagicAvatarMasterWizard's pulseCue
 * switch) -- each of which turned out to have its own gap once the wizard
 * moved to a screen where even the fallback target wasn't mounted.
 *
 * Sequencing mirrors how a real presenter's cursor works, not an instant
 * click: the target is highlighted and held for a beat (long enough to
 * read the agent's own lead-in line about it) BEFORE the actual state
 * change fires, with a short click flourish + sound landing at the exact
 * moment the action actually happens -- not at the moment the highlight
 * first appears. Confirmed live (see conversation) that today's three
 * patterns all do the highlight and the state change in the same
 * synchronous instant, which reads as nothing reacting at all once the
 * screen has already moved on.
 */

// A method can name more than one fallback, tried in order (most specific
// first) -- e.g. a wizard step's own proxy, then a page-level "something
// reacted" anchor for the rare screens where even the step-level proxy
// isn't mounted (a wizard's result/edit-scenes views, which don't render
// the step bar at all).
export type FallbackGroups = Record<string, string | string[]>;

// One small table per page/wizard, set once (not per element) by whichever
// component owns the always-mounted proxies -- e.g. MagicReelStudio calls
// setFallbackGroups("magicreel-studio", {...}) once at module scope. This is
// real domain knowledge (which proxy stands in for which not-yet-mounted
// target) that can't be derived from the DOM, so it stays explicit, but as
// ONE table per wizard rather than reimplemented inline at every call site.
const fallbackGroupsByPage = new Map<string, FallbackGroups>();

export function setFallbackGroups(pageId: string, groups: FallbackGroups) {
  fallbackGroupsByPage.set(pageId, groups);
}

export function getFallbackGroups(pageId: string): FallbackGroups | undefined {
  return fallbackGroupsByPage.get(pageId);
}

// Long enough to read a short spoken lead-in ("let's look at the Mail
// tab...") before the screen actually moves -- shorter and the highlight
// reads as a flicker; longer and a walkthrough with many quick actions in a
// row starts to feel sluggish waiting on it. Not split by nav-vs-in-place:
// which case applies isn't reliably knowable from "did we hit the exact
// target or its fallback" (a Content Studio tab IS the exact, real target
// for its own click action, but switching tabs is exactly the kind of
// bigger transition this hold exists for) -- one calibrated default, with a
// per-element `data-hl-hold="<ms>"` escape hatch for the rare case that
// needs to differ.
const DEFAULT_HOLD_MS = 2200;

let clickAudio: HTMLAudioElement | null = null;

function playClickSound() {
  try {
    if (!clickAudio) clickAudio = new Audio(clickSoundUrl);
    clickAudio.currentTime = 0;
    void clickAudio.play().catch(() => {
      // Autoplay can be blocked before the visitor's first interaction with
      // the tab -- losing the click sound once is fine, the actual action
      // must never be blocked on it.
    });
  } catch {
    // Same reasoning -- a broken/missing audio element is not a reason to
    // stop the real action from happening.
  }
}

function cssEscape(value: string): string {
  return typeof CSS !== "undefined" && CSS.escape ? CSS.escape(value) : value.replace(/["\\]/g, "\\$&");
}

function readHoldMs(el: HTMLElement): number {
  const raw = el.getAttribute("data-hl-hold");
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_HOLD_MS;
}

function armAndRun(el: HTMLElement, run: () => void) {
  scrollToTarget(el);
  const cue = el.getAttribute("data-hl-cue") === "spotlight" ? "spotlight" : "pulse";
  const armedClass = cue === "spotlight" ? "panel--spotlight" : "panel--hl-armed";
  el.classList.add(armedClass);
  const holdMs = readHoldMs(el);
  window.setTimeout(() => {
    el.classList.remove(armedClass);
    // A quick one-shot flourish landing at the exact instant the action
    // fires -- distinct from the sustained "arming" glow above -- mirrors
    // a real click's visual snap. Force-reflow so a repeated pulse on the
    // same element always restarts the animation (see useHighlight.ts's
    // applyPulse, same technique).
    el.classList.remove("panel--pulse");
    void el.offsetWidth;
    el.classList.add("panel--pulse");
    window.setTimeout(() => el.classList.remove("panel--pulse"), 700);
    playClickSound();
    run();
  }, holdMs);
}

/**
 * Called once, generically, wherever an incoming voice action is about to
 * be dispatched. `root` scopes the search to the currently mounted page (or
 * wizard) so a stale element from a page the visitor already left can never
 * be targeted. Runs `run` immediately with no visual cue if nothing --
 * neither the real target nor a fallback proxy -- is currently on screen,
 * which is exactly today's behavior for a genuinely different page that
 * hasn't mounted yet (see useProductPages.tsx's existing queue-until-mount
 * handling, unchanged by this).
 */
export function dispatchWithHighlight(
  root: ParentNode,
  component: string,
  method: string,
  run: () => void,
  fallbackGroups?: FallbackGroups
) {
  const key = `${component}:${method}`;
  const target = root.querySelector<HTMLElement>(`[data-hl="${cssEscape(key)}"]`);
  if (target) {
    armAndRun(target, run);
    return;
  }
  const groups = fallbackGroups?.[key];
  const groupList = Array.isArray(groups) ? groups : groups ? [groups] : [];
  for (const group of groupList) {
    const proxy = root.querySelector<HTMLElement>(`[data-hl-group="${cssEscape(group)}"]`);
    if (proxy) {
      armAndRun(proxy, run);
      return;
    }
  }
  run();
}
