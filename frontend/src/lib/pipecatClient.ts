import { PipecatClient } from "@pipecat-ai/client-js";
import { WebSocketTransport } from "@pipecat-ai/websocket-transport";

const VOICE_URL = import.meta.env.VITE_VOICE_URL || "http://localhost:7860";

export const pipecatClient = new PipecatClient({
  transport: new WebSocketTransport(),
  enableCam: false,
  enableMic: true,
});

export async function connectVoice(visitorId: string) {
  // Not using startBotAndConnect's automatic /start round-trip: pipecat's
  // runner builds that response's wsUrl from its own --host/--port
  // (127.0.0.1:7860 in production), which is correct for nothing outside
  // the box itself. /ws-client doesn't depend on a prior /start call for
  // anything, so we connect directly with our own correctly-proxied URL —
  // and thread visitorId through as a query param, since the plain
  // WebSocket runner path (unlike the old WebRTC one) has no body/metadata
  // channel at all.
  const wsUrl = `${VOICE_URL.replace(/^http/, "ws")}/ws-client?visitorId=${encodeURIComponent(visitorId)}`;
  await pipecatClient.connect({ wsUrl });
}

export async function disconnectVoice() {
  await pipecatClient.disconnect();
}
