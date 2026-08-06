import Icon from "../Icon";
import type { Scene } from "../../registry/studioData";

interface SceneListProps {
  scenes: Scene[];
  onChange: (scenes: Scene[]) => void;
}

export default function SceneList({ scenes, onChange }: SceneListProps) {
  function updateNarration(id: string, narration: string) {
    onChange(scenes.map((s) => (s.id === id ? { ...s, narration } : s)));
  }

  function move(index: number, dir: -1 | 1) {
    const target = index + dir;
    if (target < 0 || target >= scenes.length) return;
    const next = [...scenes];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  function remove(id: string) {
    onChange(scenes.filter((s) => s.id !== id));
  }

  return (
    <div className="scene-list">
      {scenes.map((s, i) => (
        <div key={s.id} className="scene-list__item">
          <div className="scene-list__thumb">
            <Icon name="play" size={16} />
          </div>
          <div className="scene-list__body">
            <div className="scene-list__num">Scene {i + 1}</div>
            <textarea
              className="scene-list__narration"
              value={s.narration}
              onChange={(e) => updateNarration(s.id, e.target.value)}
              rows={2}
            />
            <div className="scene-list__visual">
              <Icon name="image" size={12} /> {s.visual}
            </div>
          </div>
          <div className="scene-list__controls">
            <button onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up">
              <Icon name="chevron-down" size={13} />
            </button>
            <button onClick={() => move(i, 1)} disabled={i === scenes.length - 1} aria-label="Move down">
              <Icon name="chevron-down" size={13} />
            </button>
            <button onClick={() => remove(s.id)} aria-label="Remove scene">
              <Icon name="x" size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
