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
  await enableMicNoiseSuppression();
}

/**
 * Turns on the browser's own noise suppression, echo cancellation and auto gain
 * on the live mic track.
 *
 * A headphones-and-keyboard test (session 0aa0aaeb) produced 17 VAD triggers
 * and all 17 contained zero speech — a 100% false rate on a quiet desk. Two of
 * them ran ~1.6s, past MIN_REAL_INTERRUPTION_SECS = 0.6, so typing was being
 * promoted to a genuine barge-in and cutting the agent off mid-sentence. That
 * is the "sounds like a bad connection" symptom, produced entirely locally.
 *
 * Applied to the track rather than passed as getUserMedia constraints because
 * WebSocketTransport calls getUserMedia({ audio: true }) internally and exposes
 * no constraints hook (checked in its dist). applyConstraints() is the standard
 * MediaStreamTrack API for exactly this, needs no fork and no monkeypatching of
 * navigator.mediaDevices, and both sides of the call are public.
 *
 * Best-effort by design: constraint support varies by browser, and failing to
 * denoise is not a reason to fail a connection the user is waiting on.
 */
async function enableMicNoiseSuppression() {
  try {
    const track = pipecatClient.tracks()?.local?.audio;
    if (!track) return;
    await track.applyConstraints({
      noiseSuppression: true,
      echoCancellation: true,
      autoGainControl: true,
    });
    const applied = track.getSettings();
    console.info(
      "[mic] noise suppression:", applied.noiseSuppression,
      "| echo cancellation:", applied.echoCancellation,
      "| auto gain:", applied.autoGainControl,
    );
  } catch (err) {
    console.warn("[mic] could not apply noise constraints, continuing", err);
  }
}

export async function disconnectVoice() {
  await pipecatClient.disconnect();
}
