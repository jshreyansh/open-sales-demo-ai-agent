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
