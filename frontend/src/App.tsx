import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import StubPage from "./pages/StubPage";
import { NAV_REGISTRY } from "./registry/pages";

function findLabel(pageId: string): string {
  for (const group of NAV_REGISTRY) {
    const item = group.items.find((i) => i.id === pageId);
    if (item) return item.label;
  }
  return pageId;
}

export default function App() {
  const [activePageId, setActivePageId] = useState("dashboard");

  return (
    <div className="app-shell">
      <Sidebar activePageId={activePageId} onNavigate={setActivePageId} />
      <div className="app-shell__content">
        {activePageId === "dashboard" ? (
          <Dashboard />
        ) : (
          <StubPage label={findLabel(activePageId)} />
        )}
      </div>
    </div>
  );
}
