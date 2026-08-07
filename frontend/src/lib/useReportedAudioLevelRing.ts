import { useCallback, useEffect, useRef } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";

import { applyLevelToRing } from "./useAudioLevelRing";

// The agent's synthesized speech has no MediaStreamTrack the frontend can
// analyse directly under WebSocketTransport (WavMediaManager.tracks() has
// no "bot" key at all) — so instead of a live analyser, this ring is driven
// by real amplitude the backend already measured server-side from its TTS
// bytes and reports over the same WebSocket connection as an RTVI
// server-message (see backend/src/voice/agent_processor.py's TTSLevelReporter).
//
// If no message arrives for a bit (turn ended, or nothing ever connected),
// decay back to the resting look rather than freezing on the last value.
const SILENCE_TIMEOUT_MS = 300;

export function useReportedAudioLevelRing() {
  const ringRef = useRef<HTMLDivElement>(null);
  const silenceTimer = useRef<ReturnType<typeof setTimeout>>();

  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback((data: any) => {
      if (data?.kind !== "agent-audio-level") return;
      const el = ringRef.current;
      if (!el) return;

      applyLevelToRing(el, typeof data.level === "number" ? data.level : 0);

      if (silenceTimer.current) clearTimeout(silenceTimer.current);
      silenceTimer.current = setTimeout(() => {
        if (ringRef.current) applyLevelToRing(ringRef.current, 0);
      }, SILENCE_TIMEOUT_MS);
    }, [])
  );

  useEffect(() => {
    return () => {
      if (silenceTimer.current) clearTimeout(silenceTimer.current);
    };
  }, []);

  return ringRef;
}
