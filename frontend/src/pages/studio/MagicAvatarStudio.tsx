import { useRef, useState } from "react";
import { useRegisterComponent } from "../../lib/uiRegistry";
import { setFallbackGroups } from "../../lib/highlightBridge";
import MagicAvatarLaunchpad from "./MagicAvatarLaunchpad";
import MagicAvatarMasterWizard from "./MagicAvatarMasterWizard";
import { generateDummyScenes, type Scene } from "../../registry/studioData";

interface MagicAvatarStudioProps {
  onExit: () => void;
  onNavigate: (pageId: string) => void;
}

// Where each action falls back to when its own real, in-place target isn't
// mounted — see MagicReelStudio.tsx's identical table for the full
// reasoning. "step:N" is the StepBar pill for step N; "studio-header" is
// the always-mounted back button present on every view, including the
// result screen (which doesn't render the StepBar at all).
const MAGICAVATAR_FALLBACK_GROUPS: Record<string, string | string[]> = {
  "wizard:step-brief": ["studio-header"],
  "wizard:generate-breakdown": ["step:0", "studio-header"],
  "wizard:step-scenes": ["studio-header"],
  "wizard:step-options": ["step:2", "studio-header"],
  "wizard:select-tier-hd": ["step:2", "studio-header"],
  "wizard:select-tier-cinematic": ["step:2", "studio-header"],
  "wizard:step-generate": ["step:3", "studio-header"],
  "wizard:start-generation": ["step:3", "studio-header"],
};
setFallbackGroups("magicavatar-studio", MAGICAVATAR_FALLBACK_GROUPS);

// step/scenes/tier/generating/showResult all live here, one level up from
// the wizard, so the agent's registered actions reliably work from ANY
// starting state — including a single combined request like "start it and
// skip to generate" — even before the wizard has ever mounted. An earlier
// version moved the wizard-internal actions (step-jumps, tier, generate)
// into the child once mounted, reasoning they don't make sense before that
// anyway — but that meant requesting one before the wizard's first mount
// silently queued and never fired, while the conversation kept talking as
// if it had worked. One single, always-mounted registration point avoids
// that, same reasoning the original design already used for step/scenes.
// showResult specifically used to live as local state INSIDE the wizard
// child instead, which meant none of these 8 actions ever reset it — once
// generation finished, every one of them silently failed to navigate at
// all (the child kept rendering AvatarResult regardless of the step prop),
// confirmed as a real bug during the highlight-system audit, not just a
// missed pulse.
export default function MagicAvatarStudio({ onExit, onNavigate }: MagicAvatarStudioProps) {
  const [view, setView] = useState<"launchpad" | "wizard">("launchpad");
  const [step, setStep] = useState(0);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [tier, setTier] = useState<"hd" | "cinematic">("hd");
  const [generating, setGenerating] = useState(false);
  const [showResult, setShowResult] = useState(false);

  const latestScenes = useRef(scenes);
  latestScenes.current = scenes;
  // Set by the child once mounted (see its registerSegmentAndDirect prop),
  // so "generate-breakdown" can trigger the child's own script->scenes
  // function — it needs the child's local persona/name form fields, which
  // aren't worth lifting up just for this one action. If the child isn't
  // mounted yet, this is null and the action falls back to navigating to
  // Brief instead of silently doing nothing.
  const segmentAndDirectRef = useRef<(() => void) | null>(null);

  function goToStep(target: number) {
    if (target >= 1 && latestScenes.current.length === 0) {
      setScenes(generateDummyScenes("your specialty", "the presenter"));
    }
    setView("wizard");
    setShowResult(false);
    setStep(target);
  }

  // The visual cue (real in-place target if mounted, else the relevant
  // StepBar pill, else the always-mounted studio header — see
  // MAGICAVATAR_FALLBACK_GROUPS above) is resolved generically by
  // highlightBridge.ts before any of these ever run.
  useRegisterComponent("magicavatar-studio", "launchpad", {
    open: () => setView("launchpad"),
    "create-master": () => goToStep(0),
  });
  useRegisterComponent("magicavatar-studio", "wizard", {
    "step-brief": () => goToStep(0),
    "generate-breakdown": () => {
      if (segmentAndDirectRef.current) {
        segmentAndDirectRef.current();
      } else {
        goToStep(0);
      }
    },
    "step-scenes": () => goToStep(1),
    "step-options": () => goToStep(2),
    "select-tier-hd": () => {
      goToStep(2);
      setTier("hd");
    },
    "select-tier-cinematic": () => {
      goToStep(2);
      setTier("cinematic");
    },
    "step-generate": () => goToStep(3),
    "start-generation": () => {
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
        showResult={showResult}
        onShowResultChange={setShowResult}
        registerSegmentAndDirect={(fn) => {
          segmentAndDirectRef.current = fn;
        }}
        onBack={() => setView("launchpad")}
        onBackToAssets={onExit}
        onSubmitForReview={() => onNavigate("mlr-review")}
      />
    );
  }
  return <MagicAvatarLaunchpad onBack={onExit} onCreateMaster={() => goToStep(0)} />;
}
