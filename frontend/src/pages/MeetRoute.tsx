import { useNavigate } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import MeetingShell from "../components/MeetingShell";
import { useProductPages } from "../lib/useProductPages";
import { disconnectVoice } from "../lib/pipecatClient";
import { releaseVoiceLock } from "../lib/api";
import { getVisitorId } from "../lib/session";

// /demo/meet — Meeting Mode. Identity gating happens inside MeetingShell's
// own PreJoinScreen, unchanged from before; this just supplies the same
// underlying product-page router MeetingShell wraps as its "shared screen"
// (see useProductPages), and sends the visitor back to "/" — the landing
// chooser — once a call ends, per how this should behave end to end.
export default function MeetRoute() {
  const navigate = useNavigate();
  const { activePageId, setActivePageId, contentRef, renderPage, handleAgentAction } = useProductPages();

  return (
    <MeetingShell
      onAction={handleAgentAction}
      onLeave={() => {
        void disconnectVoice();
        // Best-effort, fast-path release — bot.py's on_client_disconnected
        // (fired by the WebSocket actually closing) is the reliable path;
        // this just frees the line a beat sooner for the common "clicked
        // hang up" case instead of waiting on that.
        void releaseVoiceLock(getVisitorId());
        navigate("/");
      }}
    >
      <div className="app-shell">
        <Sidebar activePageId={activePageId} onNavigate={setActivePageId} />
        <div className="app-shell__content" ref={contentRef}>
          {renderPage()}
        </div>
      </div>
    </MeetingShell>
  );
}
