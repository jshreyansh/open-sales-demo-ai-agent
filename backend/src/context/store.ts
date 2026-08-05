export interface SessionState {
  history: { role: "user" | "agent"; text: string }[];
  currentPage: string;
}

const sessions = new Map<string, SessionState>();

export function getSession(visitorId: string): SessionState {
  let session = sessions.get(visitorId);
  if (!session) {
    session = { history: [], currentPage: "dashboard" };
    sessions.set(visitorId, session);
  }
  return session;
}

export function saveSession(visitorId: string, session: SessionState): void {
  sessions.set(visitorId, session);
}
