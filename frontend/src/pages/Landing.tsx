import { useNavigate } from "react-router-dom";

// The chooser at "/" — replaces the old "?mode=meeting" query param with two
// real destinations. No identity gate here; that happens on whichever
// destination is actually picked (DashboardGate for /demo/dashboard,
// PreJoinScreen for /demo/meet), same as before.
//
// Primary tier is the live-call path (Join Call / Schedule for Later);
// the demo dashboard and docs are secondary, lighter-weight tiers below.
// "Schedule for Later" is disabled here for the same reason it's disabled
// on PreJoinScreen — the real scheduling flow depends on email sending
// (see the "Email for agent..." blocker), not built yet.
export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="prejoin dashboard-gate">
      <div className="dashboard-gate__card landing__card">
        <div className="prejoin__kicker">SwishX · LIVE DEMO</div>
        <h1 className="prejoin__title">AI Marketing and design agency at your fingertips</h1>
        <p className="dashboard-gate__subtitle">Pick how you'd like to explore the demo.</p>
        <div className="landing__buttons">
          <button type="button" className="prejoin__join" onClick={() => navigate("/demo/meet")}>
            Join Call
          </button>
          <button type="button" className="prejoin__join" disabled title="Coming soon">
            Schedule for Later
          </button>
        </div>
        <div className="landing__buttons landing__buttons--secondary">
          <button type="button" className="landing__btn-secondary" onClick={() => navigate("/demo/dashboard")}>
            Try & Use Demo Platform
          </button>
          <button type="button" className="landing__btn-secondary" onClick={() => navigate("/docs")}>
            Platform Documentation
          </button>
        </div>
      </div>
    </div>
  );
}
