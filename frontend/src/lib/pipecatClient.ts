import { PipecatClient } from "@pipecat-ai/client-js";
import { WebSocketTransport } from "@pipecat-ai/websocket-transport";

const VOICE_URL = import.meta.env.VITE_VOICE_URL || "http://localhost:7860";

export const pipecatClient = new PipecatClient({
  transport: new WebSocketTransport(),
  enableCam: false,
  enableMic: true,
});

export async function connectVoice(visitorId: string, name?: string, company?: string, email?: string) {
  // Not using startBotAndConnect's automatic /start round-trip: pipecat's
  // runner builds that response's wsUrl from its own --host/--port
  // (127.0.0.1:7860 in production), which is correct for nothing outside
  // the box itself. /ws-client doesn't depend on a prior /start call for
  // anything, so we connect directly with our own correctly-proxied URL —
  // and thread visitorId (and, if given, name/company/email) through as
  // query params, since the plain WebSocket runner path (unlike the old
  // WebRTC one) has no body/metadata channel at all.
  //
  // These travel here rather than only through POST /api/session/start
  // because that REST call lands in the REST API process (server.py, port
  // 8787) — a completely separate OS process from this voice connection's
  // target (bot.py, port 7860), each with its own independent in-memory
  // session store. Only what actually reaches bot.py's own process affects
  // what it speaks.
  const params = new URLSearchParams({ visitorId });
  if (name) params.set("name", name);
  if (company) params.set("company", company);
  if (email) params.set("email", email);
  const wsUrl = `${VOICE_URL.replace(/^http/, "ws")}/ws-client?${params.toString()}`;
  await pipecatClient.connect({ wsUrl });
}

export async function disconnectVoice() {
  await pipecatClient.disconnect();
}
