import { getVisitorId, type VisitorProfile } from "../lib/session";
import VisitorGateForm from "./VisitorGateForm";

interface DashboardGateProps {
  onGated: (profile: VisitorProfile) => void;
}

// /demo/dashboard's front door — same identity capture as Meeting Mode's
// pre-join screen (VisitorGateForm), but without the video-call framing
// (persona card, "Available now" badge, join countdown) that doesn't apply
// here: this isn't a call, it's a self-serve product demo with Fiona
// available in the corner chat.
export default function DashboardGate({ onGated }: DashboardGateProps) {
  return (
    <div className="prejoin dashboard-gate">
      <div className="dashboard-gate__card">
        <div className="prejoin__kicker">SwishX · Live Demo</div>
        <h1 className="prejoin__title">Try the product demo</h1>
        {/* Same rule as the pre-join hero: say what the product is before
            asking for anything, and don't hardcode the persona's name or
            gender — the persona is swappable (see persona.ts). */}
        <p className="dashboard-gate__subtitle">
          The real SwishX platform for pharma marketing content. A couple of
          details and an AI rep will meet you in chat.
        </p>
        <VisitorGateForm
          visitorId={getVisitorId()}
          path="dashboard"
          submitLabel="Continue to Dashboard"
          submittingLabel="Loading…"
          onGated={onGated}
        />
      </div>
    </div>
  );
}
