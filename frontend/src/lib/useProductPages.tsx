import { useEffect, useRef, useState } from "react";
import Dashboard from "../pages/Dashboard";
import Analytics from "../pages/Analytics";
import ContentStudio from "../pages/ContentStudio";
import BrandKit from "../pages/BrandKit";
import Approvals from "../pages/Approvals";
import StubPage from "../pages/StubPage";
import MagicReelStudio from "../pages/studio/MagicReelStudio";
import MagicAvatarStudio from "../pages/studio/MagicAvatarStudio";
import { NAV_REGISTRY } from "../registry/pages";
import { executeAction, registerComponent, unregisterComponent } from "./uiRegistry";
import type { AgentAction } from "./api";

function findLabel(pageId: string): string {
  for (const group of NAV_REGISTRY) {
    const item = group.items.find((i) => i.id === pageId);
    if (item) return item.label;
  }
  return pageId;
}

const CONTENT_STUDIO_TABS: Record<string, string> = {
  "content-studio": "All",
  "magic-video": "Video",
  "magic-aid": "Aid",
  "magic-mail": "Mail",
  "magic-canvas": "Canvas",
  "magic-doc": "Doc",
};

// The page-navigation + agent-action-dispatch machinery shared by both
// gated entry points (/demo/dashboard and /demo/meet) — each route calls
// this independently and gets its own fresh page state, since there's no
// requirement to carry "which page was open" across what are now two
// distinct visitor-facing surfaces reached from the landing chooser.
export function useProductPages() {
  const [activePageId, setActivePageId] = useState("dashboard");
  const contentRef = useRef<HTMLDivElement>(null);

  // Scroll is a real, non-simulated action (scrollBy on the actual page
  // container) — registered per current page so the agent can pan the
  // shared screen up/down the same way it triggers any other action.
  useEffect(() => {
    registerComponent(activePageId, "scroll", {
      // "smooth" silently no-ops on a negative (upward) delta here — a
      // Chromium quirk under this container's CSS `zoom` (confirmed: works
      // fine for positive/downward, and "auto" works both directions) — so
      // "auto" is the reliable choice even though it loses the glide.
      down: () => contentRef.current?.scrollBy({ top: 420, behavior: "auto" }),
      up: () => contentRef.current?.scrollBy({ top: -420, behavior: "auto" }),
    });
    return () => unregisterComponent(activePageId, "scroll");
  }, [activePageId]);

  function handleAgentAction(action: AgentAction) {
    if (action.page !== activePageId) {
      // Navigating remounts the target page, which registers its
      // components — executeAction queues until that registration lands.
      setActivePageId(action.page);
    }
    executeAction(action.page, action.component, action.method);
  }

  function renderPage() {
    if (activePageId === "dashboard") return <Dashboard />;
    if (activePageId === "analytics") return <Analytics />;
    if (activePageId === "brand-kit") return <BrandKit />;
    if (activePageId === "mlr-review") return <Approvals />;
    if (activePageId === "magicreel-studio") return <MagicReelStudio onNavigate={setActivePageId} />;
    if (activePageId === "magicavatar-studio")
      return <MagicAvatarStudio onExit={() => setActivePageId("content-studio")} onNavigate={setActivePageId} />;
    if (activePageId in CONTENT_STUDIO_TABS) {
      return (
        <ContentStudio
          key={activePageId}
          initialTab={CONTENT_STUDIO_TABS[activePageId]}
          onOpenStudio={(studioId) => setActivePageId(`${studioId}-studio`)}
        />
      );
    }
    return <StubPage label={findLabel(activePageId)} />;
  }

  return { activePageId, setActivePageId, contentRef, renderPage, handleAgentAction };
}
