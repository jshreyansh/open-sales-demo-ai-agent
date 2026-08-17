import { useEffect } from "react";

export type ActionMap = Record<string, () => void>;

export type ExecuteResult = "done" | "queued";

const registry = new Map<string, ActionMap>();

interface PendingAction {
  page: string;
  component: string;
  method: string;
}

// A real queue, not a single overwritable slot -- an autonomous walkthrough
// can fire a fresh action well within the time it takes the target page's
// component to mount and register, and a single slot silently lost
// whichever action hadn't been drained yet. Mirrors server.py's
// _pending_voice_actions, already fixed there for the identical reason
// ("a single slot silently lost whichever action hadn't been polled yet,
// which is exactly why the walkthrough's on-screen highlighting kept going
// dark mid-tour") -- this was the frontend-side half of that same bug,
// never fixed alongside it.
let pending: PendingAction[] = [];

function key(page: string, componentId: string) {
  return `${page}:${componentId}`;
}

/**
 * Called by a mounted component to expose the actions it supports.
 * Drains any pending actions now resolvable by this registration, in the
 * order they arrived -- there can be more than one if several actions were
 * queued before this component ever mounted.
 */
export function registerComponent(page: string, componentId: string, actions: ActionMap) {
  registry.set(key(page, componentId), actions);
  if (pending.length === 0) return;
  const stillPending: PendingAction[] = [];
  for (const p of pending) {
    if (p.page === page && p.component === componentId) {
      actions[p.method]?.();
    } else {
      stillPending.push(p);
    }
  }
  pending = stillPending;
}

export function unregisterComponent(page: string, componentId: string) {
  registry.delete(key(page, componentId));
}

/**
 * Runs an action if its component is already mounted. Otherwise queues it —
 * the caller is expected to have already triggered navigation to `page`;
 * once that page's component registers itself, the queued action fires.
 */
export function executeAction(page: string, componentId: string, method: string): ExecuteResult {
  const entry = registry.get(key(page, componentId));
  const fn = entry?.[method];
  if (fn) {
    fn();
    return "done";
  }
  pending.push({ page, component: componentId, method });
  return "queued";
}

/**
 * Registers this component's actions for as long as it's mounted.
 * Pass stable function references (e.g. via useCallback or refs) when the
 * actions close over changing state, to avoid needless re-registration.
 */
export function useRegisterComponent(page: string, componentId: string, actions: ActionMap) {
  useEffect(() => {
    registerComponent(page, componentId, actions);
    return () => unregisterComponent(page, componentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, componentId]);
}
