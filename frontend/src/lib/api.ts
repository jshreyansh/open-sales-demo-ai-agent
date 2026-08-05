const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8787";

export interface AgentAction {
  page: string;
  component: string;
  method: string;
}

export interface ChatResponse {
  reply: string;
  action?: AgentAction;
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

export function getDashboard() {
  return getJson<import("./types").DashboardData>("/api/dashboard");
}

export function getAnalyticsOverview() {
  return getJson<import("./types").AnalyticsOverview>("/api/analytics/overview");
}

export function getBrandKit() {
  return getJson<import("./types").BrandKitData>("/api/brand-kit");
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
