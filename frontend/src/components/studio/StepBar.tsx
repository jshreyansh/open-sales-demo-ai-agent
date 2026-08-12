interface StepBarProps {
  steps: string[];
  currentIndex: number;
  onStepClick?: (index: number) => void;
  locked?: boolean;
  // Lets the parent collect a ref per step pill — used to pulse() the pill
  // the agent is jumping to for a step-jump action, since the destination
  // step's own content isn't mounted yet at the moment the action fires
  // (this bar is, always), same reasoning as ContentStudio's engine tabs.
  onStepRef?: (index: number, el: HTMLButtonElement | null) => void;
}

export default function StepBar({ steps, currentIndex, onStepClick, locked, onStepRef }: StepBarProps) {
  return (
    <div className="studio-stepbar">
      {steps.map((label, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "upcoming";
        const clickable = !locked && onStepClick && i <= currentIndex;
        return (
          <div key={label} className="studio-stepbar__step-wrap">
            <button
              ref={(el) => onStepRef?.(i, el)}
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
