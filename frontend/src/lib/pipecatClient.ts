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
    requestData: { transport: "webrtc", body: { visitorId } },
  });
}

export async function disconnectVoice() {
  await pipecatClient.disconnect();
}
