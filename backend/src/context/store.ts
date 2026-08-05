export interface SessionState {
  history: { role: "user" | "agent"; text: string }[];
  step: number;
}

const sessions = new Map<string, SessionState>();

export function getSession(visitorId: string): SessionState {
  let session = sessions.get(visitorId);
  if (!session) {
    session = { history: [], step: 0 };
    sessions.set(visitorId, session);
  }
  return session;
}

export function saveSession(visitorId: string, session: SessionState): void {
  sessions.set(visitorId, session);
}
