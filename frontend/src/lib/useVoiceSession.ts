import { useCallback, useEffect, useRef, useState } from "react";
import { usePipecatClientMicControl, usePipecatClientTransportState, useRTVIClientEvent } from "@pipecat-ai/client-react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { claimVoiceLock, getVoiceAction, getVoiceReply, type AgentAction } from "./api";
import { getVisitorId } from "./session";
import { connectVoice } from "./pipecatClient";

const visitorId = getVisitorId();

// How long isAgentNavigating stays true with no BotStartedSpeaking to clear
// it early — a defensive ceiling for the rare action-with-no-lead-in case,
// not the normal path (see isAgentNavigating's own comment below).
const NAVIGATING_HOLD_MS = 2500;

// How long a VAD "user stopped speaking" event must hold before it's
// trusted as a real end-of-turn rather than an ordinary mid-sentence pause
// (see isAgentThinking's own comment below) — VAD's own stop_secs (bot.py)
// is tuned to ~0.3s, well inside how long a normal breath or "let me think"
// pause lasts, so treating every VAD stop as "she's thinking now" made the
// Listening state nearly invisible during real, non-continuous speech.
const THINKING_DEBOUNCE_MS = 600;

/**
 * The one place that drives the shared PipecatClient — used independently by
 * ChatWidget (Product Mode's on-demand Talk toggle) and MeetingShell
 * (Meeting Mode's always-on call). Both read/write the same underlying
 * client, so muting from either place is reflected in the other.
 */
export function useVoiceSession(
  onAction: (action: AgentAction) => void,
  onReply?: (text: string, source: "voice" | "chat") => void
) {
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
  // True for the gap between the visitor finishing and the agent's own
  // audio starting — turn commit + LLM generation + TTS enqueue, all the
  // real work that happens with nothing audible yet. Derived entirely from
  // events already received here, no backend signal needed: ends the
  // instant the agent actually starts (or immediately if the visitor starts
  // talking again first, since there's nothing left to "think about" once
  // they've moved on) — but does NOT start the instant VAD reports the
  // visitor stopped. VAD's own stop_secs (bot.py) fires on an ordinary
  // mid-sentence pause, not just a real end of turn (the backend's own
  // settle-window/fragmentation logic exists specifically because a VAD
  // stop isn't a reliable "they're done" signal) — flipping to Thinking
  // immediately made Listening nearly invisible during real, non-continuous
  // speech (confirmed live: a real call where the agent tile just looked
  // empty the whole time the prospect was actually talking). See
  // THINKING_DEBOUNCE_MS: only commits to Thinking once a stop has held
  // long enough to plausibly be real, cancelable by a resume in that window.
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  const thinkingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True right when a UI action (a page navigation/highlight) arrives from
  // the poll below, until she actually starts speaking about it (or, as a
  // safety net, NAVIGATING_HOLD_MS passes with no speech at all — an action
  // with no accompanying lead-in is rare but not impossible). Actions and
  // their lead-in almost always land within the same beat, so this is
  // usually a brief flash before Speaking (which outranks it — see
  // MeetingShell's status-badge priority) takes over, but it's exactly the
  // beat where "she just went quiet" would otherwise read as her doing
  // nothing rather than actually driving the screen.
  const [isAgentNavigating, setIsAgentNavigating] = useState(false);
  const navigatingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, useCallback(() => {
    setIsUserSpeaking(true);
    setIsAgentThinking(false);
    if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
  }, []));
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, useCallback(() => {
    setIsUserSpeaking(false);
    if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
    thinkingTimeoutRef.current = setTimeout(() => setIsAgentThinking(true), THINKING_DEBOUNCE_MS);
  }, []));
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, useCallback(() => {
    setIsAgentSpeaking(true);
    setIsAgentThinking(false);
    if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
    setIsAgentNavigating(false);
  }, []));
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, useCallback(() => setIsAgentSpeaking(false), []));

  useEffect(() => {
    return () => {
      if (navigatingTimeoutRef.current) clearTimeout(navigatingTimeoutRef.current);
      if (thinkingTimeoutRef.current) clearTimeout(thinkingTimeoutRef.current);
    };
  }, []);

  /**
   * Returns false if someone else is already on the line (see
   * server.py's _active_call) — callers need to check this and show that
   * instead of assuming the call connected.
   */
  async function connect(name?: string, company?: string, email?: string): Promise<boolean> {
    // Connect only once — reconnecting fires the client library's own
    // "Connected" handler, which wipes the whole conversation history as a
    // side effect. Once connected, treat further "connect" calls as just
    // unmuting so the shared transcript survives toggling.
    if (transportState === "disconnected") {
      const claimed = await claimVoiceLock(visitorId);
      if (!claimed) return false;
      await connectVoice(visitorId, name, company, email);
    }
    enableMic(true);
    return true;
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
      if (reply) onReplyRef.current?.(reply.text, reply.source);
      if (action) {
        setIsAgentNavigating(true);
        if (navigatingTimeoutRef.current) clearTimeout(navigatingTimeoutRef.current);
        navigatingTimeoutRef.current = setTimeout(() => setIsAgentNavigating(false), NAVIGATING_HOLD_MS);
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
    isAgentThinking,
    isAgentNavigating,
  };
}
