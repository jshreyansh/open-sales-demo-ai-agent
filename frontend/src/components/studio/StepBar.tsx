interface StepBarProps {
  steps: string[];
  currentIndex: number;
  onStepClick?: (index: number) => void;
  locked?: boolean;
  // Every step pill is always mounted regardless of which step is active,
  // making it the natural fallback target (data-hl-group) for any action
  // whose own real, in-place target isn't rendered right now — see
  // highlightBridge.ts. `hlGroupPrefix` scopes the group key per wizard
  // (e.g. "step" for MagicReel, matching MAGICREEL_FALLBACK_GROUPS' "step:N"
  // entries) so two different wizards sharing this component never collide.
  // `dataHl` optionally gives a specific pill its own literal, primary
  // data-hl target (used for the one step per wizard — the first one —
  // that has no natural "Continue into it" button of its own to carry that
  // key instead).
  hlGroupPrefix: string;
  dataHl?: (index: number) => string | undefined;
}

export default function StepBar({ steps, currentIndex, onStepClick, locked, hlGroupPrefix, dataHl }: StepBarProps) {
  return (
    <div className="studio-stepbar">
      {steps.map((label, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "upcoming";
        const clickable = !locked && onStepClick && i <= currentIndex;
        return (
          <div key={label} className="studio-stepbar__step-wrap">
            <button
              data-hl={dataHl?.(i)}
              data-hl-group={`${hlGroupPrefix}:${i}`}
              className={`studio-stepbar__step studio-stepbar__step--${state}`}
              onClick={() => clickable && onStepClick?.(i)}
              disabled={!clickable}
            >
              <span className="studio-stepbar__circle">{state === "done" ? "✓" : i + 1}</span>
              <span className="studio-stepbar__label">{label}</span>
            </button>
            {i < steps.length - 1 && <span className="studio-stepbar__connector" />}
          </div>
        );
      })}
    </div>
  );
}
