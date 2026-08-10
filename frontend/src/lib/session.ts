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

export interface VisitorProfile {
  name: string;
  company: string;
  email: string;
}

const PROFILE_KEY = "visitor_profile";

// Set once the shared gate form (VisitorGateForm) collects and validates
// name/company/work-email — same sessionStorage lifetime as visitor_id
// above, so it resets on the same "fresh tab = fresh visit" boundary. Lets
// both gated routes (/demo/dashboard and /demo/meet) skip straight past the
// gate if the visitor already passed it once in this tab, instead of
// re-prompting on every navigation between them.
export function getVisitorProfile(): VisitorProfile | null {
  const raw = sessionStorage.getItem(PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as VisitorProfile;
  } catch {
    return null;
  }
}

export function setVisitorProfile(profile: VisitorProfile): void {
  sessionStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}
