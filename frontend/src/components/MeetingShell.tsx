import { useEffect, useState } from "react";
import { usePipecatClientMicControl, usePipecatClientTransportState } from "@pipecat-ai/client-react";
import MeetIcon from "./MeetIcons";

interface MeetingShellProps {
  children: React.ReactNode;
  onLeave: () => void;
}

const MEETING_CODE = "demo-call-pnx";

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000 * 30);
    return () => clearInterval(id);
  }, []);
  return now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function MeetingShell({ children, onLeave }: MeetingShellProps) {
  const time = useClock();
  const [cameraOn, setCameraOn] = useState(true);
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const transportState = usePipecatClientTransportState();
  const joined = transportState === "connected" || transportState === "ready";

  return (
    <div className="meet">
      <div className="meet__topbar">
        <div className="meet__topbar-left">
          <span>{time}</span>
          <span className="meet__dot">|</span>
          <span>{MEETING_CODE}</span>
          <MeetIcon name="info" size={15} />
        </div>
        <div className="meet__topbar-right">
          <span className="meet__presenting">
            <span className="meet__avatar meet__avatar--tiny">Y</span>
            You (Presenting)
          </span>
          <span className="meet__people">
            <MeetIcon name="people" size={16} /> 2
          </span>
        </div>
      </div>

      {!joined && (
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
            <div className="meet__tile-label">You</div>
          </div>
          <div className="meet__tile meet__tile--agent">
            <span className="meet__mic-badge">
              <MeetIcon name="mic" size={13} />
            </span>
            <div className="meet__avatar meet__avatar--agent">E</div>
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
          <MeetIcon name="camera" />
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
