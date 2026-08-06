import { useCallback, useEffect, useRef, useState } from "react";
import { usePipecatClientMicControl, usePipecatClientTransportState, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { getVoiceAction, getVoiceReply, type AgentAction } from "./api";
import { getVisitorId } from "./session";
import { connectVoice } from "./pipecatClient";

const visitorId = getVisitorId();

/**
 * The one place that drives the shared PipecatClient — used independently by
 * ChatWidget (Product Mode's on-demand Talk toggle) and MeetingShell
 * (Meeting Mode's always-on call). Both read/write the same underlying
 * client, so muting from either place is reflected in the other.
 */
export function useVoiceSession(onAction: (action: AgentAction) => void, onReply?: (text: string) => void) {
  const transportState = usePipecatClientTransportState();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();

  const connecting = transportState === "connecting" || transportState === "authenticating" || transportState === "initializing";
  const voiceConnected = transportState === "connected" || transportState === "ready";

  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;
  const onReplyRef = useRef(onReply);
  onReplyRef.current = onReply;

  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setIsUserSpeaking(true), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setIsUserSpeaking(false), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setIsAgentSpeaking(true), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setIsAgentSpeaking(false), []));

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

  // Voice-triggered UI actions (and, for callers that want it, the reply
  // text itself) arrive out-of-band — the voice process is a separate
  // service from the REST API — so poll while a call is active. Actions
  // fire the instant they're seen: the backend already delays reporting an
  // action until the right moment (right after a short spoken lead-in, not
  // at the end of the whole reply), so there's nothing left to wait for
  // here. An older version of this hook re-delayed actions until
  // BotStoppedSpeaking, which made sense before that backend-side ordering
  // existed — but a lead-in and its explanation play as one continuous TTS
  // session with only a few milliseconds' gap between them, invisible to
  // this poll's 800ms cadence, so that logic would've just delayed the
  // action all over again until the entire reply finished.
  useEffect(() => {
    if (!voiceConnected) return;
    const id = setInterval(async () => {
      const [action, reply] = await Promise.all([
        getVoiceAction(visitorId).catch(() => null),
        onReplyRef.current ? getVoiceReply(visitorId).catch(() => null) : Promise.resolve(null),
      ]);
      if (reply) onReplyRef.current?.(reply);
      if (action) onActionRef.current(action);
    }, 800);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceConnected]);

  return {
    transportState,
    connecting,
    voiceConnected,
    isMicEnabled,
    enableMic,
    connect,
    mute,
    isUserSpeaking,
    isAgentSpeaking,
  };
}
