import { useEffect, useRef, useState } from "react";
import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import { useVoiceSession } from "../lib/useVoiceSession";
import { useAudioLevelRing } from "../lib/useAudioLevelRing";
import { useReportedAudioLevelRing } from "../lib/useReportedAudioLevelRing";
import { raiseHand, startSession, type AgentAction } from "../lib/api";
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
  const [cameraOn, setCameraOn] = useState(true);
  const [handRaised, setHandRaised] = useState(false);
  const [countdown, setCountdown] = useState(JOIN_COUNTDOWN_SECS);
  // Gates the join countdown (and, transitively, the voice connect effect
  // below) behind PreJoinScreen — the visitor picks a rep and gives their
  // name there first, a real call doesn't auto-connect before that.
  const [joined, setJoined] = useState(false);
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
  const connectStarted = useRef(false);
  useEffect(() => {
    if (!joined) return;
    if (countdown > 0) return;
    if (connectStarted.current) return;
    connectStarted.current = true;
    void connect().then(() => mute());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, countdown]);

  // The non-interrupting alternative to talking over the agent: posts to the
  // voice process (a separate process from this UI) via the REST API, which
  // polls for it and hands off after finishing its current explanation,
  // rather than cutting off mid-sentence like a real VAD interruption would.
  function handleRaiseHand() {
    setHandRaised(true);
    void raiseHand(visitorId);
    window.setTimeout(() => setHandRaised(false), 2000);
  }

  // Priming the session with the visitor's name before the voice pipeline
  // ever connects means the very first thing it says is already
  // personalized ("Hi Alex, I'm Fiona...") instead of generic — the voice
  // process reads back whatever greeting this call seeded (see
  // backend/src/context/store.py's start_session). Fire-and-forget: the
  // 5-second join countdown plus pipeline setup time is ample margin for
  // this request to land first, and if it doesn't, the call still works —
  // it just falls back to the generic non-personalized greeting.
  function handleJoin(name: string) {
    void startSession(visitorId, name);
    setJoined(true);
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

      <div className="meet__controls">
        <button
          className={`meet__ctrl ${!isMicEnabled ? "meet__ctrl--off" : ""}`}
          onClick={() => enableMic(!isMicEnabled)}
        >
          <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} />
        </button>
        <button className={`meet__ctrl ${!cameraOn ? "meet__ctrl--off" : ""}`} onClick={() => setCameraOn((v) => !v)}>
          <MeetIcon name={cameraOn ? "camera" : "camera-off"} />
        </button>
        <button className="meet__ctrl meet__ctrl--active">
          <MeetIcon name="screen-share" />
        </button>
        <button className="meet__ctrl">
          <MeetIcon name="captions" />
        </button>
        <button
          className={`meet__ctrl ${handRaised ? "meet__ctrl--pressed" : ""}`}
          onClick={handleRaiseHand}
          title="Raise hand — the agent will finish its point, then let you ask your question"
        >
          <MeetIcon name="hand" />
        </button>
        <button className="meet__ctrl">
          <MeetIcon name="dots" />
        </button>
        <button className="meet__ctrl meet__ctrl--hangup" onClick={onLeave}>
          <MeetIcon name="hangup" />
        </button>
      </div>
    </div>
  );
}
