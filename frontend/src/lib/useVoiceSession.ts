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
  const isAgentSpeakingRef = useRef(false);
  isAgentSpeakingRef.current = isAgentSpeaking;

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => setIsUserSpeaking(true), []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => setIsUserSpeaking(false), []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => setIsAgentSpeaking(true), []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setIsAgentSpeaking(false), []));

  // The backend decides an action's text and its navigation in the same
  // turn, but the action shouldn't land until she's actually said the part
  // where she's navigating — otherwise the screen jumps while she's still
  // mid-sentence explaining. Hold it until she goes quiet.
  const pendingActionRef = useRef<AgentAction | null>(null);
  const silenceTimerRef = useRef<number | null>(null);
  const safetyTimerRef = useRef<number | null>(null);

  function clearActionTimers() {
    if (silenceTimerRef.current) {
      window.clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (safetyTimerRef.current) {
      window.clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  }

  function flushPendingAction() {
    clearActionTimers();
    const action = pendingActionRef.current;
    if (!action) return;
    pendingActionRef.current = null;
    onActionRef.current(action);
  }

  useEffect(() => {
    if (isAgentSpeaking) {
      // Speaking again (e.g. the next sentence) — a brief pause between
      // sentences shouldn't count as "done", so cancel any pending flush.
      if (silenceTimerRef.current) {
        window.clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
      return;
    }
    if (!pendingActionRef.current) return;
    silenceTimerRef.current = window.setTimeout(flushPendingAction, 400);
    return () => {
      if (silenceTimerRef.current) window.clearTimeout(silenceTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAgentSpeaking]);

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
  // service from the REST API — so poll while a call is active.
  useEffect(() => {
    if (!voiceConnected) return;
    const id = setInterval(async () => {
      const [action, reply] = await Promise.all([
        getVoiceAction(visitorId).catch(() => null),
        onReplyRef.current ? getVoiceReply(visitorId).catch(() => null) : Promise.resolve(null),
      ]);
      if (reply) onReplyRef.current?.(reply);
      if (!action) return;
      if (isAgentSpeakingRef.current) {
        pendingActionRef.current = action;
        // Safety net in case BotStoppedSpeaking never arrives — don't hold
        // a navigation forever.
        clearActionTimers();
        safetyTimerRef.current = window.setTimeout(flushPendingAction, 8000);
      } else {
        onActionRef.current(action);
      }
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
