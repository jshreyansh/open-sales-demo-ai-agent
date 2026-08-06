import { useState } from "react";
import SceneInspector from "./SceneInspector";
import SceneList from "./SceneList";
import type { Scene } from "../../registry/studioData";

interface ScenesWorkspaceProps {
  scenes: Scene[];
  onChange: (scenes: Scene[]) => void;
  brandName: string;
  subtitle: string;
}

export default function ScenesWorkspace({ scenes, onChange, brandName, subtitle }: ScenesWorkspaceProps) {
  const [tab, setTab] = useState<"timeline" | "narration">("timeline");
  const words = scenes.reduce((sum, s) => sum + s.narration.split(/\s+/).filter(Boolean).length, 0);
  const seconds = Math.round(words / 2.3);

  return (
    <div>
      <div className="scenes-workspace__head">
        <div className="tabs-row scenes-workspace__tabs">
          <button className={`tab-item ${tab === "timeline" ? "tab-item--active" : ""}`} onClick={() => setTab("timeline")}>
            Timeline
          </button>
          <button className={`tab-item ${tab === "narration" ? "tab-item--active" : ""}`} onClick={() => setTab("narration")}>
            Narration
          </button>
        </div>
        <button className="btn scenes-workspace__voice-btn">Change voice</button>
      </div>
      <div className="scenes-workspace__meta">
        {scenes.length} scenes · {words} words · ~{seconds}s spoken
      </div>

      {tab === "timeline" ? (
        <SceneInspector scenes={scenes} brandName={brandName} subtitle={subtitle} onChange={onChange} />
      ) : (
        <SceneList scenes={scenes} onChange={onChange} />
      )}
    </div>
  );
}
