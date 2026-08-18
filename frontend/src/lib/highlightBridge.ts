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

// Called once, synchronously, right before a page's next highlight is about
// to arm -- lets a page proactively tidy up its own state (e.g. close a
// still-open modal) BEFORE the highlight/hold begins, not after. Registered
// once per page (like setFallbackGroups above), keyed by pageId.
//
// Content Studio needed this: its preview-modal close logic used to live
// inside the format's own `open()` handler, which only runs at the very END
// of the highlight hold (when the click actually fires) -- so while the
// NEXT format's card/tab was being highlighted and held for 2.2s, the
// PREVIOUS format's modal just sat there fully open the whole time,
// hiding the highlight behind it. Closing here, before the hold starts,
// means the highlight is visible against the real page for virtually the
// entire hold instead of only appearing once the old modal finally closes.
const beforeArmByPage = new Map<string, () => void>();

export function registerBeforeArm(pageId: string, fn: () => void) {
  beforeArmByPage.set(pageId, fn);
}

function getBeforeArm(pageId: string): (() => void) | undefined {
  return beforeArmByPage.get(pageId);
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

// Dims everything except the highlighted target. A real overlay element
// rather than the target's own box-shadow spread (the previous approach) --
// box-shadow gets clipped by the nearest ancestor with overflow != visible,
// and .app-shell__content (the div wrapping just the current page, not the
// sidebar) has overflow-y: auto for scrolling, which silently computes
// overflow-x to auto too and clips the spread there. Confirmed live: the dim
// stopped exactly at the sidebar's edge, and a sidebar-triggered navigation
// (which highlights something on the SIDEBAR, outside .app-shell__content
// entirely) got no dim at all.
//
// Appended as a child of .app-shell specifically, not document.body --
// .app-shell is the one common ancestor of both the sidebar and the page
// content, un-clipped (no overflow set), so a position:fixed child of it
// covers both. In Meeting Mode, .app-shell sits inside .meet__stage-inner,
// whose own transform (see index.css) makes IT the containing block for
// position:fixed descendants -- so the same fixed-position overlay
// automatically confines itself to just the shared-screen pane there
// instead of covering the visitor's whole browser window, with no extra
// code needed here.
function setScrim(el: HTMLElement, visible: boolean) {
  const container = el.closest(".app-shell") ?? document.body;
  let scrim = container.querySelector<HTMLDivElement>(":scope > .hl-scrim");
  if (!scrim) {
    if (!visible) return;
    scrim = document.createElement("div");
    scrim.className = "hl-scrim";
    container.appendChild(scrim);
  }
  scrim.classList.toggle("hl-scrim--visible", visible);
}

// Converts a viewport-relative rect (what getBoundingClientRect always
// returns, regardless of any ancestor's zoom/transform) into "relative to
// the actual position:fixed containing block" coordinates. .meet__stage-inner's
// transform (see index.css) makes IT that containing block inside Meeting
// Mode's shared screen -- so a fixed-position ring positioned with raw
// viewport coordinates would land offset by however far .meet__stage-inner
// itself sits from the true top-left of the browser window. No-op in
// Product Mode, where no such ancestor exists and the containing block
// really is the viewport (offset 0,0, zoom 1).
//
// zoom is the second, separate correction needed only in Meeting Mode:
// .meet__stage-inner's `zoom: 0.9` (see index.css) recomputes layout at that
// factor for EVERY descendant, including the ring itself (it's a
// position:fixed child of .app-shell, which sits inside .meet__stage-inner).
// getBoundingClientRect() always reports real, already-zoomed screen
// pixels -- but a CSS length assigned to an element living inside the
// zoomed ancestor gets scaled by that same factor AGAIN at render time.
// Left uncorrected, the ring's own left/top/width/height (already real
// pixels) get multiplied by 0.9 a second time, landing it 10% smaller and
// pulled toward the container's top-left corner -- confirmed live: this
// exact offset, on every highlight in Meeting Mode, not just the sidebar
// (the box-shadow-on-target approach this replaced never hit it, since a
// box-shadow is the target's own property and rides its own zoom
// naturally). Dividing the real-pixel delta by this factor before writing
// it to the ring's style is what the browser's own re-scaling expects.
function fixedContainingBlockOffset(el: HTMLElement): { left: number; top: number; zoom: number } {
  const containingBlock = el.closest<HTMLElement>(".meet__stage-inner");
  if (!containingBlock) return { left: 0, top: 0, zoom: 1 };
  const rect = containingBlock.getBoundingClientRect();
  const zoomValue = parseFloat(getComputedStyle(containingBlock).zoom);
  return { left: rect.left, top: rect.top, zoom: Number.isFinite(zoomValue) && zoomValue > 0 ? zoomValue : 1 };
}

function getOrCreateRing(container: Element): HTMLDivElement {
  let ring = container.querySelector<HTMLDivElement>(":scope > .hl-ring");
  if (!ring) {
    ring = document.createElement("div");
    ring.className = "hl-ring";
    container.appendChild(ring);
  }
  return ring;
}

// Sizes/positions the ring to exactly match the target's own box, every
// time it's (re)armed -- a floating overlay rather than a box-shadow on
// the target itself (the previous approach), for the same reason the dim
// scrim became one: box-shadow gets clipped by the nearest ancestor with
// overflow != visible. .sidebar__nav (overflow-y: auto, for its scrollable
// item list) clipped the ring's glow at its own edges -- confirmed live,
// the ring was invisible for the whole hold on a sidebar item, even though
// the (already-fixed) dim scrim showed correctly, since only the scrim had
// been moved out of the clipped container so far.
function positionRing(ring: HTMLDivElement, target: HTMLElement) {
  const targetRect = target.getBoundingClientRect();
  const offset = fixedContainingBlockOffset(target);
  const targetRadius = getComputedStyle(target).borderRadius;
  // The real-pixel delta gets divided by the containing block's own zoom
  // factor -- see fixedContainingBlockOffset's docstring for why: the ring
  // is itself rendered inside that same zoomed ancestor in Meeting Mode, so
  // its assigned CSS pixels get scaled by that factor a second time.
  ring.style.left = `${(targetRect.left - offset.left) / offset.zoom}px`;
  ring.style.top = `${(targetRect.top - offset.top) / offset.zoom}px`;
  ring.style.width = `${targetRect.width / offset.zoom}px`;
  ring.style.height = `${targetRect.height / offset.zoom}px`;
  ring.style.borderRadius = targetRadius;
}

function armAndRun(el: HTMLElement, run: () => void) {
  scrollToTarget(el);
  const container = el.closest(".app-shell") ?? document.body;
  const ring = getOrCreateRing(container);

  // scrollToTarget above is a SMOOTH (animated) scroll -- it doesn't finish
  // in the same tick, it keeps sliding the page for a few hundred more ms.
  // Measuring the target's rect only once, right here, would freeze the
  // ring at wherever the target happened to be BEFORE that animation
  // finished, while the target itself keeps moving to its final resting
  // position -- confirmed live: the ring landed increasingly offset from
  // the real target the further it had to scroll to get there. Tracking on
  // every frame for the whole hold (cheap: one getBoundingClientRect + a
  // style write per frame, for a single element) keeps the ring glued to
  // the target regardless of how long the scroll animation takes, and
  // incidentally also covers any other reason the target might move
  // (a resize, a CSS transition elsewhere on the page) for free.
  let trackingFrame = 0;
  function track() {
    positionRing(ring, el);
    trackingFrame = requestAnimationFrame(track);
  }
  track();

  ring.classList.add("hl-ring--visible");
  el.classList.add("hl-target-lift");
  setScrim(el, true);
  const holdMs = readHoldMs(el);
  window.setTimeout(() => {
    cancelAnimationFrame(trackingFrame);
    positionRing(ring, el);
    ring.classList.remove("hl-ring--visible");
    el.classList.remove("hl-target-lift");
    setScrim(el, false);
    // A quick one-shot flourish landing at the exact instant the action
    // fires -- distinct from the sustained "arming" glow above -- mirrors
    // a real click's visual snap. Force-reflow so a repeated pulse on the
    // same element always restarts the animation.
    ring.classList.remove("hl-ring--pulse");
    void ring.offsetWidth;
    ring.classList.add("hl-ring--pulse");
    window.setTimeout(() => ring.classList.remove("hl-ring--pulse"), 700);
    playClickSound();
    run();
  }, holdMs);
}

/**
 * Called once, generically, wherever an incoming voice action is about to
 * be dispatched. `root` scopes the search to the currently mounted page (or
 * wizard) so a stale element from a page the visitor already left can never
 * be targeted. Runs `run` immediately with no visual cue if nothing --
 * neither the real target, a page-specific fallback proxy, nor the sidebar
 * nav fallback below -- is currently on screen.
 */
export function dispatchWithHighlight(
  root: ParentNode,
  component: string,
  method: string,
  run: () => void,
  fallbackGroups?: FallbackGroups,
  pageId?: string
) {
  // Runs BEFORE anything below arms/holds -- see registerBeforeArm's own
  // docstring for why this has to happen first, not at click-time.
  if (pageId) getBeforeArm(pageId)?.();
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
  // Universal last resort for a genuine cross-page jump: the destination
  // page's own component isn't mounted yet (we're still showing whatever
  // page we're jumping FROM), but the sidebar nav item for it is always
  // there regardless of which page is active -- see Sidebar.tsx's
  // `data-hl-group={`${item.id}-nav`}`. Named by pageId (the actual
  // registry page id), not `key`, since there's no per-component fallback
  // table to register for every plain top-level page -- one universal
  // naming convention instead.
  if (pageId) {
    const navProxy = root.querySelector<HTMLElement>(`[data-hl-group="${cssEscape(pageId)}-nav"]`);
    if (navProxy) {
      armAndRun(navProxy, run);
      return;
    }
  }
  run();
}
