import { useEffect, useRef } from "react";
import { usePipecatClientMicControl, usePipecatClientTransportState } from "@pipecat-ai/client-react";
import { getVoiceAction, type AgentAction } from "./api";
import { getVisitorId } from "./session";
import { connectVoice } from "./pipecatClient";

const visitorId = getVisitorId();

/**
 * The one place that drives the shared PipecatClient — used independently by
 * ChatWidget (Product Mode's on-demand Talk toggle) and MeetingShell
 * (Meeting Mode's always-on call). Both read/write the same underlying
 * client, so muting from either place is reflected in the other.
 */
export function useVoiceSession(onAction: (action: AgentAction) => void) {
  const transportState = usePipecatClientTransportState();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();

  const connecting = transportState === "connecting" || transportState === "authenticating" || transportState === "initializing";
  const voiceConnected = transportState === "connected" || transportState === "ready";

  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

  async function connect() {
    // Connect only once — reconnecting fires the client library's own
    // "Connected" handler, which wipes the whole conversation history as a
    // side effect. Once connected, treat further "connect" calls as just
    // unmuting so the shared transcript survives toggling.
    if (transportState === "disconnected") {
      await connectVoice(visitorId);
    }
    enableMic(true);
  }

  function mute() {
    enableMic(false);
  }

  // Voice-triggered UI actions arrive out-of-band (the voice process is a
  // separate service from the REST API) — poll while a call is active.
  useEffect(() => {
    if (!voiceConnected) return;
    const id = setInterval(async () => {
      const action = await getVoiceAction(visitorId).catch(() => null);
      if (action) onActionRef.current(action);
    }, 800);
    return () => clearInterval(id);
  }, [voiceConnected]);

  return { transportState, connecting, voiceConnected, isMicEnabled, enableMic, connect, mute };
}
