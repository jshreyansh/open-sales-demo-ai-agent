interface StepBarProps {
  steps: string[];
  currentIndex: number;
  onStepClick?: (index: number) => void;
  locked?: boolean;
}

export default function StepBar({ steps, currentIndex, onStepClick, locked }: StepBarProps) {
  return (
    <div className="studio-stepbar">
      {steps.map((label, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "upcoming";
        const clickable = !locked && onStepClick && i <= currentIndex;
        return (
          <div key={label} className="studio-stepbar__step-wrap">
            <button
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
