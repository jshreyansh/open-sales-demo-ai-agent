import { useState } from "react";
import MagicAvatarLaunchpad from "./MagicAvatarLaunchpad";
import MagicAvatarMasterWizard from "./MagicAvatarMasterWizard";

interface MagicAvatarStudioProps {
  onExit: () => void;
}

export default function MagicAvatarStudio({ onExit }: MagicAvatarStudioProps) {
  const [view, setView] = useState<"launchpad" | "wizard">("launchpad");

  if (view === "wizard") {
    return <MagicAvatarMasterWizard onBack={() => setView("launchpad")} onDone={() => setView("launchpad")} />;
  }
  return <MagicAvatarLaunchpad onBack={onExit} onCreateMaster={() => setView("wizard")} />;
}
