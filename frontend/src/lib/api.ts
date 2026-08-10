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
 * Called when the prospect toggles the hand-raise button in Meeting Mode —
 * the non-interrupting alternative to talking over the agent. Raising and
 * lowering are both explicit clicks (see MeetingShell): the voice process
 * (a separate process from this REST API) polls this state and hands off at
 * the next sentence boundary rather than cutting the agent off outright, and
 * never lowers it on its own — only another call to this with raised=false
 * does.
 */
export async function setHandRaiseState(visitorId: string, raised: boolean): Promise<void> {
  await fetch(`${API_URL}/api/hand-raise/${visitorId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raised }),
  });
}

/**
 * Called by the shared gate form (VisitorGateForm) the moment a valid work
 * email is entered — lets a returning visitor skip straight past the
 * name/company fields instead of retyping what's already on file.
 */
export async function lookupVisitor(email: string): Promise<{ known: boolean; name?: string; company?: string }> {
  const res = await fetch(`${API_URL}/api/visitor/lookup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) return { known: false };
  return res.json();
}

export type GateStatus = "allowed" | "blocked_personal_email";

/**
 * Called once per gate submission — allowed or blocked — by the shared gate
 * form. This is what actually populates the admin panel's identity log
 * (see gate_log.py); a blocked personal-email attempt is reported the same
 * way, just with no name/company (the form never asks for those until the
 * email passes).
 */
export async function reportGateAttempt(
  visitorId: string,
  email: string,
  path: "dashboard" | "meet",
  status: GateStatus,
  name?: string,
  company?: string,
): Promise<void> {
  await fetch(`${API_URL}/api/visitor/gate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId, email, name, company, path, status }),
  });
}

export interface AdminVisitor {
  email: string;
  name: string | null;
  company: string | null;
  first_seen_at: string;
  last_seen_at: string;
  session_count: number;
  paths_tried: string[];
  ever_blocked: boolean;
}

export interface AdminAttempt {
  id: number;
  visitor_id: string;
  email: string;
  name: string | null;
  company: string | null;
  path: string;
  status: string;
  created_at: string;
}

export function getAdminVisitors() {
  return getJson<AdminVisitor[]>("/api/admin/visitors");
}

export function getAdminAttempts() {
  return getJson<AdminAttempt[]>("/api/admin/attempts");
}

export interface AdminStats {
  total_visitors: number;
  total_sessions: number;
  blocked_attempts: number;
  dashboard_sessions: number;
  meet_sessions: number;
  recent_visitors: AdminVisitor[];
}

export function getAdminStats() {
  return getJson<AdminStats>("/api/admin/stats");
}

export interface AdminSession {
  id: number;
  visitor_id: string;
  path: string;
  status: string;
  created_at: string;
}

export interface AdminVisitorDetail {
  email: string;
  name: string | null;
  company: string | null;
  first_seen_at: string;
  last_seen_at: string;
  sessions: AdminSession[];
}

export function getAdminVisitorDetail(email: string) {
  return getJson<AdminVisitorDetail>(`/api/admin/visitors/${encodeURIComponent(email)}`);
}

export interface TranscriptTurn {
  role: "user" | "agent";
  text: string;
  created_at: string;
}

export function getAdminTranscript(visitorId: string) {
  return getJson<TranscriptTurn[]>(`/api/admin/transcript/${encodeURIComponent(visitorId)}`);
}

/**
 * Called once, right when the visitor fills in their name, company, and work
 * email on Meeting Mode's pre-join screen — before the voice connection
 * starts. Explicitly (re)starts the backend session with those, so the
 * opening greeting (spoken by the voice pipeline) addresses them by name
 * from the first word, and company/email are already on hand as the first
 * real MEDDIC data point instead of the agent having to go ask for them.
 */
export async function startSession(visitorId: string, name: string, company: string, email: string): Promise<void> {
  await fetch(`${API_URL}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId, name, company, email }),
  });
}

/**
 * The voicebot process handles one real call at a time (see server.py's
 * _active_call for why) — called right before connecting voice so a second
 * caller gets a clear "busy" answer instead of silently degrading whoever's
 * already on the line. Returns false if someone else is already connected.
 */
export async function claimVoiceLock(visitorId: string): Promise<boolean> {
  const res = await fetch(`${API_URL}/api/voice-lock/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  return !!data.ok;
}

/** Called on explicit hangup — best-effort; bot.py's on_client_disconnected
 * is the reliable release path (see server.py), this just frees the line
 * faster for the common "clicked hang up" case instead of waiting on that. */
export async function releaseVoiceLock(visitorId: string): Promise<void> {
  await fetch(`${API_URL}/api/voice-lock/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId }),
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
