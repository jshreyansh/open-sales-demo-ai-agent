import { useState } from "react";
import Sidebar from "../components/Sidebar";
import TopBar from "../components/TopBar";
import ChatWidget from "../components/ChatWidget";
import DashboardGate from "../components/DashboardGate";
import { useProductPages } from "../lib/useProductPages";
import { getVisitorProfile } from "../lib/session";

// /demo/dashboard — Product Mode, now gated the same way Meeting Mode
// already was (per Dushyant's feedback: casual clicks vs. a real MEDDIC data
// point). No "explicit join" step needed here the way a live call has one —
// once identity is known this tab (see getVisitorProfile), the dashboard is
// just there, no extra confirmation click.
export default function DashboardRoute() {
  const [gated, setGated] = useState(() => getVisitorProfile() !== null);
  const { activePageId, setActivePageId, contentRef, renderPage, handleAgentAction } = useProductPages();

  if (!gated) {
    return <DashboardGate onGated={() => setGated(true)} />;
  }

  return (
    <div className="app-shell">
      <Sidebar activePageId={activePageId} onNavigate={setActivePageId} />
      <div className="app-shell__content" ref={contentRef}>
        <TopBar />
        {renderPage()}
      </div>
      <ChatWidget currentPage={activePageId} onAction={handleAgentAction} />
    </div>
  );
}
