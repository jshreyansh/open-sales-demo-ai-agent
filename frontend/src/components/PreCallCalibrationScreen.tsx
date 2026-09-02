import type { PacePrior } from "../lib/api";

interface PreCallCalibrationScreenProps {
  // undefined covers both "walk me through everything" and skip — both
  // leave the adaptive-interaction evidence counters at their cold-start
  // baseline (see backend context/store.py's start_session).
  onChoose: (pacePrior: PacePrior | undefined) => void;
}

// One question, three choices, one skip — deliberately not a
// questionnaire. This is only a STARTING prior for the adaptive
// interaction policy (see runtime.py's _interaction_note); real
// conversation behavior keeps overriding it turn by turn, so getting this
// one answer "wrong" just means a slightly slower start, not a locked-in
// mode for the whole call.
export default function PreCallCalibrationScreen({ onChoose }: PreCallCalibrationScreenProps) {
  return (
    <div className="postcall">
      <div className="postcall__card">
        <h1 className="postcall__title">One quick thing before we start.</h1>
        <p className="postcall__subtitle">What would help most today?</p>
        <div className="postcall__choices postcall__choices--stacked">
          <button type="button" className="postcall__choice" onClick={() => onChoose("fast")}>
            Quick, no-fluff overview
          </button>
          <button type="button" className="postcall__choice" onClick={() => onChoose(undefined)}>
            Walk me through everything
          </button>
          <button type="button" className="postcall__choice" onClick={() => onChoose("self_directed")}>
            I know exactly what I want to see
          </button>
        </div>
        <button type="button" className="postcall__skip" onClick={() => onChoose(undefined)}>
          Skip
        </button>
      </div>
    </div>
  );
}
