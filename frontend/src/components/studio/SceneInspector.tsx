import { useState } from "react";
import Icon from "../Icon";
import type { Scene } from "../../registry/studioData";

interface SceneInspectorProps {
  scenes: Scene[];
  brandName: string;
  subtitle: string;
  onChange: (scenes: Scene[]) => void;
}

function updateField(scenes: Scene[], id: string, patch: Partial<Scene>) {
  return scenes.map((s) => (s.id === id ? { ...s, ...patch } : s));
}

export default function SceneInspector({ scenes, brandName, subtitle, onChange }: SceneInspectorProps) {
  const [index, setIndex] = useState(0);
  const scene = scenes[Math.min(index, scenes.length - 1)];
  if (!scene) return null;

  function patch(fields: Partial<Scene>) {
    onChange(updateField(scenes, scene.id, fields));
  }

  return (
    <div className="scene-inspector">
      <div className="scene-inspector__preview">
        <div className="scene-inspector__player">
          <div className="scene-inspector__logo">{brandName.slice(0, 1)}</div>
          <div className="scene-inspector__title">{brandName}</div>
          <div className="scene-inspector__subtitle">{subtitle}</div>
        </div>
        <div className="scene-inspector__playbar">
          <Icon name="play" size={13} />
          <span className="scene-inspector__time">0:00 / 0:50</span>
          <div className="scene-inspector__scrub" />
          <Icon name="chevron-down" size={13} />
        </div>
        <p className="stub-page__note scene-inspector__caption">
          Scene visuals are generated on render — this preview shows timing, cards, and on-screen text.
        </p>
      </div>

      <div className="scene-inspector__panel">
        <div className="scene-inspector__nav">
          <span>Scene {index + 1}</span>
          <div className="scene-inspector__nav-btns">
            <button onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}>
              ← prev
            </button>
            <button onClick={() => setIndex((i) => Math.min(scenes.length - 1, i + 1))} disabled={index === scenes.length - 1}>
              next →
            </button>
          </div>
        </div>

        <div className="scene-field scene-field--narration">
          <div className="scene-field__label">
            <Icon name="mic" size={13} /> Narration
          </div>
          <textarea rows={3} value={scene.narration} onChange={(e) => patch({ narration: e.target.value })} />
        </div>

        <div className="scene-field scene-field--visual">
          <div className="scene-field__label">
            <Icon name="image" size={13} /> Visual prompt
          </div>
          <textarea rows={3} value={scene.visual} onChange={(e) => patch({ visual: e.target.value })} />
        </div>

        <div className="scene-field scene-field--negative">
          <div className="scene-field__label">
            <Icon name="ban" size={13} /> Negative prompt
          </div>
          <textarea rows={2} value={scene.negativePrompt} onChange={(e) => patch({ negativePrompt: e.target.value })} />
        </div>

        <div className="scene-field scene-field--text">
          <div className="scene-field__label">
            <span className="scene-field__t-icon">T</span> On-screen text {scene.onScreenText ? "(1)" : "(0)"}
            {scene.hasCitation && <span className="scene-field__citation">+ 1 source citation (not editable)</span>}
          </div>
          {scene.onScreenText ? (
            <div className="scene-field__overlay-row">
              <input value={scene.onScreenText} onChange={(e) => patch({ onScreenText: e.target.value })} />
              <select defaultValue="caption">
                <option value="caption">Caption — plain text</option>
              </select>
              <button className="scene-field__remove" onClick={() => patch({ onScreenText: "" })}>
                <Icon name="x" size={13} />
              </button>
            </div>
          ) : (
            <button className="btn" onClick={() => patch({ onScreenText: brandName })}>
              + Add overlay
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
