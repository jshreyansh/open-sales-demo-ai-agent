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
        <p className="dashboard-gate__subtitle">
          A couple of details first — Fiona will be right there in chat once you're in.
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
