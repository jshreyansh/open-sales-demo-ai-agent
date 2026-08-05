import { useEffect } from "react";

export type ActionMap = Record<string, () => void>;

export type ExecuteResult = "done" | "queued";

const registry = new Map<string, ActionMap>();

interface PendingAction {
  page: string;
  component: string;
  method: string;
}

let pending: PendingAction | null = null;

function key(page: string, componentId: string) {
  return `${page}:${componentId}`;
}

/**
 * Called by a mounted component to expose the actions it supports.
 * If an action was queued waiting for this exact component to mount
 * (e.g. the agent navigated here first), it fires immediately.
 */
export function registerComponent(page: string, componentId: string, actions: ActionMap) {
  registry.set(key(page, componentId), actions);
  if (pending && pending.page === page && pending.component === componentId) {
    const fn = actions[pending.method];
    pending = null;
    fn?.();
  }
}

export function unregisterComponent(page: string, componentId: string) {
  registry.delete(key(page, componentId));
}

/**
 * Runs an action if its component is already mounted. Otherwise queues it —
 * the caller is expected to have already triggered navigation to `page`;
 * once that page's component registers itself, the queued action fires.
 * There is only ever one pending action: a newer one replaces an older one
 * that never got the chance to run.
 */
export function executeAction(page: string, componentId: string, method: string): ExecuteResult {
  const entry = registry.get(key(page, componentId));
  const fn = entry?.[method];
  if (fn) {
    fn();
    return "done";
  }
  pending = { page, component: componentId, method };
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
