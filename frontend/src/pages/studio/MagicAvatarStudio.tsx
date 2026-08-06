import { useRef, useState } from "react";
import { useRegisterComponent } from "../../lib/uiRegistry";
import MagicAvatarLaunchpad from "./MagicAvatarLaunchpad";
import MagicAvatarMasterWizard from "./MagicAvatarMasterWizard";
import { generateDummyScenes, type Scene } from "../../registry/studioData";

interface MagicAvatarStudioProps {
  onExit: () => void;
}

// step and scenes live here, one level up from the wizard itself, so the
// agent's registered actions can jump straight to any step — including
// switching out of the Launchpad — even before the wizard has ever mounted.
export default function MagicAvatarStudio({ onExit }: MagicAvatarStudioProps) {
  const [view, setView] = useState<"launchpad" | "wizard">("launchpad");
  const [step, setStep] = useState(0);
  const [scenes, setScenes] = useState<Scene[]>([]);

  const latestScenes = useRef(scenes);
  latestScenes.current = scenes;

  function goToStep(target: number) {
    // Skipping straight past the brief (e.g. jumping to Options) would
    // otherwise show an empty scene list — auto-fill it, same as clicking
    // through "Next" on the brief step normally would have.
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
    "step-brief": () => goToStep(0),
    "step-scenes": () => goToStep(1),
    "step-options": () => goToStep(2),
    "step-generate": () => goToStep(3),
  });

  if (view === "wizard") {
    return (
      <MagicAvatarMasterWizard
        step={step}
        onStepChange={setStep}
        scenes={scenes}
        onScenesChange={setScenes}
        onBack={() => setView("launchpad")}
        onDone={() => setView("launchpad")}
      />
    );
  }
  return <MagicAvatarLaunchpad onBack={onExit} onCreateMaster={() => goToStep(0)} />;
}
