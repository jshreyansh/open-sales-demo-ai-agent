const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8787";

export interface AgentAction {
  page: string;
  component: string;
  method: string;
}

export interface ChatResponse {
  reply: string;
  action?: AgentAction;
  // Present only alongside "action" — a short transition ("let me pull that
  // up") meant to be shown/said before the action fires, with "reply" (the
  // actual explanation) following after.
  lead_in?: string;
}

export async function sendMessage(
  visitorId: string,
  message: string,
  currentPage: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId, message, currentPage }),
  });
  if (!res.ok) throw new Error(`chat request failed: ${res.status}`);
  return res.json();
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

/** Polled while a voice call is active — returns {} when there's nothing pending. */
export async function getVoiceAction(visitorId: string): Promise<AgentAction | null> {
  const result = await getJson<Partial<AgentAction>>(`/api/voice-action/${visitorId}`);
  return result.page && result.component && result.method ? (result as AgentAction) : null;
}

/**
 * Polled while a voice call is active — the reply text the agent just spoke.
 * Pipecat's own bot-transcription RTVI event isn't reliably emitted for the
 * voice pipeline's one-shot (non-streaming) reply, so this side-channel is
 * what actually gets the spoken words into the chat transcript.
 */
export async function getVoiceReply(visitorId: string): Promise<string | null> {
  const result = await getJson<{ reply?: string }>(`/api/voice-reply/${visitorId}`);
  return result.reply || null;
}

/**
 * Called when the prospect clicks the hand-raise button in Meeting Mode — the
 * non-interrupting alternative to talking over the agent. The voice process
 * (a separate process from this REST API) polls for this and, instead of
 * cutting the agent off mid-sentence like a real interruption would, lets it
 * finish its current explanation and then hands off explicitly.
 */
export async function raiseHand(visitorId: string): Promise<void> {
  await fetch(`${API_URL}/api/hand-raise/${visitorId}`, { method: "POST" });
}

/**
 * Called once, right when the visitor picks a name on Meeting Mode's
 * pre-join screen — before the voice connection starts. Explicitly
 * (re)starts the backend session with that name so the opening greeting
 * (spoken by the voice pipeline) addresses them by it from the first word,
 * instead of waiting for them to volunteer it mid-conversation. Always
 * starts fresh rather than resuming whatever session visitorId already had
 * (it persists in localStorage across visits) — a new "Join" is a new call.
 */
export async function startSession(visitorId: string, name: string): Promise<void> {
  await fetch(`${API_URL}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId, name }),
  });
}

export function getDashboard() {
  return getJson<import("./types").DashboardData>("/api/dashboard");
}

export function getAnalyticsOverview() {
  return getJson<import("./types").AnalyticsOverview>("/api/analytics/overview");
}

export function getBrandKit() {
  return getJson<import("./types").BrandKitData>("/api/brand-kit");
}

export function getApprovals() {
  return getJson<import("./types").ApprovalsData>("/api/approvals");
}

export async function saveBrandKit(data: import("./types").BrandKitData) {
  const res = await fetch(`${API_URL}/api/brand-kit`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`save brand-kit failed: ${res.status}`);
  return res.json() as Promise<import("./types").BrandKitData>;
}
