import { useEffect, useRef, useState } from "react";
import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import { useVoiceSession } from "../lib/useVoiceSession";
import { useAudioLevelRing } from "../lib/useAudioLevelRing";
import { useReportedAudioLevelRing } from "../lib/useReportedAudioLevelRing";
import { claimVoiceLock, setHandRaiseState, startSession, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import MeetIcon from "./MeetIcons";
import PreJoinScreen from "./PreJoinScreen";
import { AGENT_NAME, AGENT_INITIAL, AGENT_PHOTO } from "../lib/persona";

const visitorId = getVisitorId();

interface MeetingShellProps {
  children: React.ReactNode;
  onLeave: () => void;
  onAction: (action: AgentAction) => void;
}

const MEETING_CODE = "demo-call-pnx";
const JOIN_COUNTDOWN_SECS = 5;

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000 * 30);
    return () => clearInterval(id);
  }, []);
  return now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// The box-shadow (edge stroke + soft glow) is driven by whichever ring
// source the caller passes in — useAudioLevelRing off a real audio track
// for "You" (the visitor's own mic), useReportedAudioLevelRing off the
// backend's server-computed loudness for the agent (its synthesized speech
// has no MediaStreamTrack to analyse under WebSocketTransport, see that
// hook's docstring). Not a fixed pulse animation either way, so it only
// shows when they're actually making sound. Set on the avatar circle
// itself, not a separate larger ring element with a gap.
function TileAvatar({
  ringRef,
  photo,
  letter,
  avatarClassName,
}: {
  ringRef: React.RefObject<HTMLDivElement>;
  photo?: string;
  letter: string;
  avatarClassName: string;
}) {
  return (
    <div className={`meet__avatar ${avatarClassName}`} ref={ringRef}>
      {photo ? <img src={photo} alt="" className="meet__avatar-img" /> : letter}
    </div>
  );
}

export default function MeetingShell({ children, onLeave, onAction }: MeetingShellProps) {
  const time = useClock();
  const [handRaised, setHandRaised] = useState(false);
  const [countdown, setCountdown] = useState(JOIN_COUNTDOWN_SECS);
  // Gates the join countdown (and, transitively, the voice connect effect
  // below) behind PreJoinScreen — the visitor picks a rep and gives their
  // name there first, a real call doesn't auto-connect before that.
  const [joined, setJoined] = useState(false);
  // Captured from PreJoinScreen — threaded into connect() below so the
  // voice pipeline's own process (see the connect-effect's comment) gets it
  // directly, rather than relying on a side channel it can't see.
  const [visitorName, setVisitorName] = useState<string | undefined>(undefined);
  const [visitorCompany, setVisitorCompany] = useState<string | undefined>(undefined);
  const [visitorEmail, setVisitorEmail] = useState<string | undefined>(undefined);
  const { voiceConnected, isMicEnabled, enableMic, connect, mute } = useVoiceSession(onAction);
  // "You" tile: real local mic MediaStreamTrack, analysed client-side. The
  // agent's tile: WebSocketTransport exposes no "bot" track at all (its
  // audio never becomes an inspectable MediaStreamTrack), so its ring is
  // driven by real server-computed loudness reported over RTVI instead —
  // see useReportedAudioLevelRing's docstring. Neither is the same as
  // isUserSpeaking/isAgentSpeaking (those are VAD start/stop booleans).
  const localAudioTrack = usePipecatClientMediaTrack("audio", "local");
  const youRingRef = useAudioLevelRing(localAudioTrack);
  const agentRingRef = useReportedAudioLevelRing();

  // The agent "joins" only after the countdown finishes, which itself only
  // starts once the visitor has actually picked a rep and given their name
  // on PreJoinScreen — a real call doesn't connect the instant the tab
  // loads, it shows the join intro first.
  useEffect(() => {
    if (!joined) return;
    if (countdown <= 0) return;
    const id = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [joined, countdown]);

  // This is the only place that triggers the voice connection in Meeting
  // Mode — a real call auto-joins, it isn't a button the visitor clicks.
  // connect() itself enables the mic (that's the right default for Product
  // Mode's explicit "Talk" button) — Meeting Mode wants the opposite default,
  // muted until the visitor deliberately unmutes, so mute right after.
  //
  // visitorName is passed straight into connect() (which threads it onto
  // the WebSocket URL as a query param, see pipecatClient.ts) rather than
  // relying on the earlier POST /api/session/start alone — that REST call
  // lands in the REST API process (server.py, port 8787), a completely
  // separate OS process from the voice pipeline it needs to reach (bot.py,
  // port 7860), each with its own independent in-memory session store. Only
  // what actually reaches bot.py's own process affects what it speaks.
  const connectStarted = useRef(false);
  useEffect(() => {
    if (!joined) return;
    if (countdown > 0) return;
    if (connectStarted.current) return;
    connectStarted.current = true;
    void connect(visitorName, visitorCompany, visitorEmail).then(() => mute());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, countdown]);

  // The backend can end a call on its own now (see agent_processor.py's
  // idle-timeout watcher — someone who mutes and walks away without
  // hanging up), not just the visitor clicking hangup. Without this, that
  // would leave the visitor sitting on the "Our agent is joining..." banner
  // for a call that's actually already over, which reads as a bug rather
  // than an intentional end. Once the call has genuinely connected, a drop
  // back to disconnected is treated the same as clicking hangup.
  const wasConnected = useRef(false);
  useEffect(() => {
    if (voiceConnected) {
      wasConnected.current = true;
      return;
    }
    if (wasConnected.current) {
      wasConnected.current = false;
      onLeave();
    }
  }, [voiceConnected, onLeave]);

  // Spacebar toggles mute, same convention as Google Meet/Zoom — but only
  // once actually connected, and never while focus is in a text field (the
  // chat input rendered in `children`), where a space is just a space.
  useEffect(() => {
    if (!voiceConnected) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      e.preventDefault();
      enableMic(!isMicEnabled);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [voiceConnected, isMicEnabled, enableMic]);

  // A real toggle, not a momentary press: the visitor raises their hand and
  // it stays raised — same as actually raising a hand in a room — until they
  // click it again to lower it. Nothing auto-resets this; the agent hands
  // off once (see agent_processor.py's _hand_ack_sent) but never lowers the
  // hand itself, since only the visitor really knows when their question's
  // been answered.
  function handleToggleHandRaise() {
    const next = !handRaised;
    setHandRaised(next);
    void setHandRaiseState(visitorId, next);
  }

  // Claimed here, at the moment of clicking Join, not later when connect()
  // actually opens the WebSocket after the countdown — reserving the slot
  // immediately (rather than leaving a 5-second window where a second
  // visitor could also slip through the countdown) is what PreJoinScreen's
  // busy message is actually protecting. connect() below claims again for
  // the same visitor when it runs, which is a harmless no-op re-claim, not
  // a second real check.
  //
  // The actual voice personalization happens via connect(visitorName) in
  // the effect above. startSession here is a separate, secondary thing: it
  // seeds the REST API process's own session store with the same name, in
  // case anything reads it from that side later (e.g. a future text
  // transcript in Meeting Mode) — Meeting Mode has no such surface today,
  // so this is forward-looking, not load-bearing.
  async function handleJoin(name: string, company: string, email: string): Promise<boolean> {
    const claimed = await claimVoiceLock(visitorId);
    if (!claimed) return false;
    void startSession(visitorId, name, company, email);
    setVisitorName(name);
    setVisitorCompany(company);
    setVisitorEmail(email);
    setJoined(true);
    return true;
  }

  if (!joined) {
    return <PreJoinScreen onJoin={handleJoin} />;
  }

  return (
    <div className="meet">
      {countdown > 0 && (
        <div className="meet__intro">
          <img src={AGENT_PHOTO} alt="" className="meet__intro-avatar meet__intro-avatar-img" />
          <div className="meet__intro-text">{AGENT_NAME} is joining for the demo…</div>
          <div className="meet__intro-count">{countdown}</div>
        </div>
      )}

      <div className="meet__topbar">
        <div className="meet__topbar-left">
          <span>{time}</span>
          <span className="meet__dot">|</span>
          <span>{MEETING_CODE}</span>
          <MeetIcon name="info" size={15} />
        </div>
        <div className="meet__topbar-right">
          <span className="meet__presenting">
            <span className="meet__avatar meet__avatar--tiny meet__avatar--tiny-agent">
              <img src={AGENT_PHOTO} alt="" className="meet__avatar-img" />
            </span>
            {AGENT_NAME} (Presenting)
          </span>
          <span className="meet__people">
            <MeetIcon name="people" size={16} /> 2
          </span>
        </div>
      </div>

      {countdown <= 0 && !voiceConnected && (
        <div className="meet__banner">Our agent is joining {MEETING_CODE}…</div>
      )}

      <div className="meet__body">
        <div className="meet__stage">
          <div className="meet__stage-inner">{children}</div>
        </div>

        <div className="meet__rail">
          <div className="meet__tile meet__tile--you">
            <span className="meet__mic-badge">
              <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} size={13} />
            </span>
            <TileAvatar ringRef={youRingRef} letter="Y" avatarClassName="meet__avatar--tile meet__avatar--you" />
            <div className="meet__tile-label">You</div>
          </div>
          <div className="meet__tile meet__tile--agent">
            <span className="meet__mic-badge">
              <MeetIcon name="mic" size={13} />
            </span>
            <TileAvatar ringRef={agentRingRef} photo={AGENT_PHOTO} letter={AGENT_INITIAL} avatarClassName="meet__avatar--tile meet__avatar--agent" />
            <div className="meet__tile-label">{AGENT_NAME}</div>
          </div>
        </div>
      </div>

      {/* Only mic, hand-raise, and hangup are actually wired to real
          behavior right now — camera, screen-share, captions, and the
          overflow menu were removed rather than left as dead, unusable
          buttons (see the "remove useless controls" task). */}
      <div className="meet__controls-hint">
        Tip: press <kbd>Space</kbd> to mute or unmute
      </div>
      <div className="meet__controls">
        <button
          className={`meet__ctrl ${!isMicEnabled ? "meet__ctrl--off" : ""}`}
          onClick={() => enableMic(!isMicEnabled)}
        >
          <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} />
        </button>
        <button
          className={`meet__ctrl ${handRaised ? "meet__ctrl--pressed" : ""}`}
          onClick={handleToggleHandRaise}
          title={
            handRaised
              ? "Lower hand"
              : "Raise hand — the agent will finish its point, then let you ask your question"
          }
        >
          <MeetIcon name="hand" />
        </button>
        <button className="meet__ctrl meet__ctrl--hangup" onClick={onLeave}>
          <MeetIcon name="hangup" />
        </button>
      </div>
    </div>
  );
}
