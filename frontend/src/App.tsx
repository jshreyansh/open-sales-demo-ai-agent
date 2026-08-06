import { useState } from "react";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import MeetingShell from "./components/MeetingShell";
import ChatWidget from "./components/ChatWidget";
import Dashboard from "./pages/Dashboard";
import Analytics from "./pages/Analytics";
import ContentStudio from "./pages/ContentStudio";
import BrandKit from "./pages/BrandKit";
import Approvals from "./pages/Approvals";
import StubPage from "./pages/StubPage";
import MagicReelStudio from "./pages/studio/MagicReelStudio";
import MagicAvatarStudio from "./pages/studio/MagicAvatarStudio";
import { NAV_REGISTRY } from "./registry/pages";
import { executeAction } from "./lib/uiRegistry";
import { disconnectVoice, pipecatClient } from "./lib/pipecatClient";
import type { AgentAction } from "./lib/api";

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

function getInitialMode(): "product" | "meeting" {
  const params = new URLSearchParams(window.location.search);
  return params.get("mode") === "meeting" ? "meeting" : "product";
}

export default function App() {
  const [activePageId, setActivePageId] = useState("dashboard");
  const [mode, setMode] = useState<"product" | "meeting">(getInitialMode);

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
    if (activePageId === "magicavatar-studio") return <MagicAvatarStudio onExit={() => setActivePageId("content-studio")} />;
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

  const productShell = (
    <div className="app-shell">
      <Sidebar activePageId={activePageId} onNavigate={setActivePageId} />
      <div className="app-shell__content">
        {mode === "product" && <TopBar />}
        {renderPage()}
      </div>
    </div>
  );

  return (
    <PipecatClientProvider client={pipecatClient}>
      {/* Renders the actual <audio> element that plays the bot's TTS speech —
          without this, voice replies are received but never played back. */}
      <PipecatClientAudio />
      {mode === "meeting" ? (
        <MeetingShell
          onAction={handleAgentAction}
          onLeave={() => {
            void disconnectVoice();
            const url = new URL(window.location.href);
            url.searchParams.delete("mode");
            window.history.replaceState(null, "", url.toString());
            setMode("product");
          }}
        >
          {productShell}
        </MeetingShell>
      ) : (
        <>
          {productShell}
          <ChatWidget currentPage={activePageId} onAction={handleAgentAction} />
        </>
      )}
    </PipecatClientProvider>
  );
}
