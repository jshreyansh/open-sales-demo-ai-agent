import { useState } from "react";
import Sidebar from "./components/Sidebar";
import MeetingShell from "./components/MeetingShell";
import Dashboard from "./pages/Dashboard";
import Analytics from "./pages/Analytics";
import ContentStudio from "./pages/ContentStudio";
import BrandKit from "./pages/BrandKit";
import StubPage from "./pages/StubPage";
import { NAV_REGISTRY } from "./registry/pages";

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

  function renderPage() {
    if (activePageId === "dashboard") return <Dashboard />;
    if (activePageId === "analytics") return <Analytics />;
    if (activePageId === "brand-kit") return <BrandKit />;
    if (activePageId in CONTENT_STUDIO_TABS) {
      return <ContentStudio key={activePageId} initialTab={CONTENT_STUDIO_TABS[activePageId]} />;
    }
    return <StubPage label={findLabel(activePageId)} />;
  }

  const product = (
    <div className="app-shell">
      <Sidebar activePageId={activePageId} onNavigate={setActivePageId} />
      <div className="app-shell__content">{renderPage()}</div>
    </div>
  );

  if (mode === "meeting") {
    return (
      <MeetingShell
        onLeave={() => {
          const url = new URL(window.location.href);
          url.searchParams.delete("mode");
          window.history.replaceState(null, "", url.toString());
          setMode("product");
        }}
      >
        {product}
      </MeetingShell>
    );
  }

  return product;
}
