const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8787";

export interface AgentAction {
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
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ visitorId, message }),
  });
  if (!res.ok) throw new Error(`chat request failed: ${res.status}`);
  return res.json();
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
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
