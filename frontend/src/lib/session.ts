const KEY = "visitor_id";

// sessionStorage, not localStorage: this is a demo meant to feel like a
// fresh first-contact sales call every time, not a real product where
// returning-visitor continuity is a feature. localStorage persisted the
// same visitor_id (and therefore the same backend conversation history)
// indefinitely across visits — close the tab, reopen days later, and the
// agent would still "remember" everything from before. sessionStorage
// keeps that identity only for as long as the tab stays open: a same-tab
// refresh mid-conversation doesn't lose anything, but closing the tab and
// coming back starts genuinely fresh, which is what was actually wanted.
export function getVisitorId(): string {
  let id = sessionStorage.getItem(KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(KEY, id);
  }
  return id;
}
