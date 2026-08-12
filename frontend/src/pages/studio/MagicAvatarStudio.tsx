import { useRef, useState } from "react";
import { useRegisterComponent } from "../../lib/uiRegistry";
import MagicAvatarLaunchpad from "./MagicAvatarLaunchpad";
import MagicAvatarMasterWizard from "./MagicAvatarMasterWizard";
import { generateDummyScenes, type Scene } from "../../registry/studioData";

interface MagicAvatarStudioProps {
  onExit: () => void;
  onNavigate: (pageId: string) => void;
}

// step/scenes/tier/generating all live here, one level up from the wizard,
// so the agent's registered actions reliably work from ANY starting state —
// including a single combined request like "start it and skip to generate"
// — even before the wizard has ever mounted. An earlier version moved the
// wizard-internal actions (step-jumps, tier, generate) into the child
// once mounted, reasoning they don't make sense before that anyway — but
// that meant requesting one before the wizard's first mount silently
// queued and never fired, while the conversation kept talking as if it
// had worked. One single, always-mounted registration point avoids that,
// same reasoning the original design already used for step/scenes.
export default function MagicAvatarStudio({ onExit, onNavigate }: MagicAvatarStudioProps) {
  const [view, setView] = useState<"launchpad" | "wizard">("launchpad");
  const [step, setStep] = useState(0);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [tier, setTier] = useState<"hd" | "cinematic">("hd");
  const [generating, setGenerating] = useState(false);

  const latestScenes = useRef(scenes);
  latestScenes.current = scenes;
  // Set by the child once mounted (see its registerSegmentAndDirect prop),
  // so "generate-breakdown" can trigger the child's own script->scenes
  // function — it needs the child's local persona/name form fields, which
  // aren't worth lifting up just for this one action. If the child isn't
  // mounted yet, this is null and the action falls back to navigating to
  // Brief instead of silently doing nothing.
  const segmentAndDirectRef = useRef<(() => void) | null>(null);
  // Same pattern (see child's registerCue prop) — the child owns the actual
  // DOM refs for its StepBar pills, tier cards, and generate buttons, so it
  // hands up a "pulse whichever target matches this action id" function
  // instead of lifting all those refs to the parent. Null if the wizard
  // hasn't mounted yet (nothing to pulse in that case — the wizard mounting
  // for the first time is itself the visible change).
  const cueRef = useRef<((actionId: string) => void) | null>(null);
  function pulseCue(actionId: string) {
    cueRef.current?.(actionId);
  }

  function goToStep(target: number) {
    if (target >= 1 && latestScenes.current.length === 0) {
      setScenes(generateDummyScenes("your specialty", "the presenter"));
    }
    setView("wizard");
    setStep(target);
  }

  useRegisterComponent("magicavatar-studio", "launchpad", {
    open: () => setView("launchpad"),
    "create-master": () => goToStep(0),
  });
  useRegisterComponent("magicavatar-studio", "wizard", {
    "step-brief": () => {
      pulseCue("step-brief");
      goToStep(0);
    },
    "generate-breakdown": () => {
      pulseCue("generate-breakdown");
      if (segmentAndDirectRef.current) {
        segmentAndDirectRef.current();
      } else {
        goToStep(0);
      }
    },
    "step-scenes": () => {
      pulseCue("step-scenes");
      goToStep(1);
    },
    "step-options": () => {
      pulseCue("step-options");
      goToStep(2);
    },
    "select-tier-hd": () => {
      pulseCue("select-tier-hd");
      goToStep(2);
      setTier("hd");
    },
    "select-tier-cinematic": () => {
      pulseCue("select-tier-cinematic");
      goToStep(2);
      setTier("cinematic");
    },
    "step-generate": () => {
      pulseCue("step-generate");
      goToStep(3);
    },
    "start-generation": () => {
      pulseCue("start-generation");
      goToStep(3);
      setGenerating(true);
    },
  });

  if (view === "wizard") {
    return (
      <MagicAvatarMasterWizard
        step={step}
        onStepChange={setStep}
        scenes={scenes}
        onScenesChange={setScenes}
        tier={tier}
        onTierChange={setTier}
        generating={generating}
        onGeneratingChange={setGenerating}
        registerSegmentAndDirect={(fn) => {
          segmentAndDirectRef.current = fn;
        }}
        registerCue={(fn) => {
          cueRef.current = fn;
        }}
        onBack={() => setView("launchpad")}
        onBackToAssets={onExit}
        onSubmitForReview={() => onNavigate("mlr-review")}
      />
    );
  }
  return <MagicAvatarLaunchpad onBack={onExit} onCreateMaster={() => goToStep(0)} />;
}
