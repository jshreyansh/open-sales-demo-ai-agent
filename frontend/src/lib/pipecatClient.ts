import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const VOICE_URL = import.meta.env.VITE_VOICE_URL || "http://localhost:7860";

export const pipecatClient = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableCam: false,
  enableMic: true,
});

export async function connectVoice(visitorId: string) {
  await pipecatClient.startBotAndConnect({
    endpoint: `${VOICE_URL}/start`,
    requestData: {
      transport: "webrtc",
      body: { visitorId },
      // Without this, the browser's own RTCPeerConnection gathers only
      // "host" candidates — its own local network interfaces. On a machine
      // running something like Tailscale, that's *only* Tailscale's virtual
      // addresses (confirmed live: 100.64.0.0/10 CGNAT + fd7a: ULA ranges),
      // none of which our server can ever reach — ICE sits in "checking"
      // forever and audio never connects, even though signaling succeeds.
      // This flag makes pipecat's runner return a STUN server in its /start
      // response, which the client library applies automatically. The
      // matching server-side fix (bot.py's ICE monkeypatch) was already in
      // place; this was the missing other half.
      enableDefaultIceServers: true,
    },
  });
}

export async function disconnectVoice() {
  await pipecatClient.disconnect();
}
