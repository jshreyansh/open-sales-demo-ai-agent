import { useEffect, useState } from "react";
import Icon from "../Icon";

interface GenerationScreenProps {
  subjectLabel: string;
  sourceLabel: string;
  onDone: () => void;
}

const PHASES = ["Preparing", "Directing visuals", "Assembling scenes", "Adding subtitles", "Finalizing"];

/**
 * Fake but convincing progress — no real render job behind this. Mirrors the
 * real product's GenerationProgress screen's shape (persona framing, phase
 * text, live %, "safe to leave" reassurance) without any of the actual SSE/
 * job-polling machinery, since this is a mockup for showing the user flow,
 * not a real pipeline.
 */
export default function GenerationScreen({ subjectLabel, sourceLabel, onDone }: GenerationScreenProps) {
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const id = setInterval(() => {
      setProgress((p) => {
        const next = Math.min(100, p + Math.random() * 10 + 4);
        if (next >= 100) {
          window.clearInterval(id);
          setTimeout(() => setDone(true), 500);
        }
        return next;
      });
    }, 450);
    return () => window.clearInterval(id);
  }, []);

  const phaseIndex = Math.min(PHASES.length - 1, Math.floor((progress / 100) * PHASES.length));

  if (done) {
    return (
      <div className="gen-screen gen-screen--done">
        <div className="gen-screen__done-icon">
          <Icon name="check-circle" size={36} />
        </div>
        <h2>Your {subjectLabel} is ready</h2>
        <p className="gen-screen__sub">Generated and saved to your Content Library.</p>
        <div className="gen-screen__thumb">
          <Icon name="play" size={22} />
        </div>
        <button className="btn-primary" onClick={onDone}>
          Back to Content Studio
        </button>
      </div>
    );
  }

  return (
    <div className="gen-screen">
      <div className="gen-screen__persona">
        <div className="gen-screen__avatar" />
        <p>
          Your Creative Producer is crafting your {subjectLabel}…
          <span className="gen-screen__source">{sourceLabel}</span>
        </p>
      </div>
      <div className="gen-screen__status">
        <div className="gen-screen__status-row">
          <span className="gen-screen__phase">{PHASES[phaseIndex]}…</span>
          <span className="gen-screen__pct">{Math.round(progress)}%</span>
        </div>
        <div className="progress-bar">
          <div className="progress-bar__fill" style={{ width: `${progress}%`, background: "var(--accent)" }} />
        </div>
        <p className="gen-screen__hint">Typically takes a couple of minutes — sit tight.</p>
      </div>
      <div className="gen-screen__safe">
        <Icon name="check-circle" size={14} />
        You can safely leave this page — we'll email you the moment it's ready.
      </div>
    </div>
  );
}
