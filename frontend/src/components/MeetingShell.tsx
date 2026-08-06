import { useEffect, useRef, useState } from "react";
import { useVoiceSession } from "../lib/useVoiceSession";
import type { AgentAction } from "../lib/api";
import MeetIcon from "./MeetIcons";

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

function VoiceDots({ active }: { active: boolean }) {
  return (
    <div className={`voice-dots ${active ? "voice-dots--active" : ""}`}>
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}

export default function MeetingShell({ children, onLeave, onAction }: MeetingShellProps) {
  const time = useClock();
  const [cameraOn, setCameraOn] = useState(true);
  const [countdown, setCountdown] = useState(JOIN_COUNTDOWN_SECS);
  const { voiceConnected, isMicEnabled, enableMic, connect, isUserSpeaking, isAgentSpeaking } =
    useVoiceSession(onAction);

  // Emma "joins" only after the countdown finishes — a real call doesn't
  // connect the instant the tab loads, it shows the join intro first.
  useEffect(() => {
    if (countdown <= 0) return;
    const id = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [countdown]);

  // This is the only place that triggers the voice connection in Meeting
  // Mode — a real call auto-joins, it isn't a button the visitor clicks.
  const connectStarted = useRef(false);
  useEffect(() => {
    if (countdown > 0) return;
    if (connectStarted.current) return;
    connectStarted.current = true;
    void connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countdown]);

  return (
    <div className="meet">
      {countdown > 0 && (
        <div className="meet__intro">
          <div className="meet__intro-avatar">E</div>
          <div className="meet__intro-text">Emma is joining for the demo…</div>
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
            <span className="meet__avatar meet__avatar--tiny meet__avatar--tiny-agent">E</span>
            Emma · AI Agent (Presenting)
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
            <div className="meet__avatar meet__avatar--you">Y</div>
            <VoiceDots active={isUserSpeaking} />
            <div className="meet__tile-label">You</div>
          </div>
          <div className="meet__tile meet__tile--agent">
            <span className="meet__mic-badge">
              <MeetIcon name="mic" size={13} />
            </span>
            <div className="meet__avatar meet__avatar--agent">E</div>
            <VoiceDots active={isAgentSpeaking} />
            <div className="meet__tile-label">Emma · AI Agent</div>
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
        <button className="meet__ctrl">
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
