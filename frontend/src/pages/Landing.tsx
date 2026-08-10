import { useNavigate } from "react-router-dom";

// The chooser at "/" — replaces the old "?mode=meeting" query param with two
// real destinations. No identity gate here; that happens on whichever
// destination is actually picked (DashboardGate for /demo/dashboard,
// PreJoinScreen for /demo/meet), same as before.
export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="prejoin dashboard-gate">
      <div className="dashboard-gate__card landing__card">
        <div className="prejoin__kicker">SwishX · ContentIQ</div>
        <h1 className="prejoin__title">AI Marketing and design agency at your fingertips</h1>
        <p className="dashboard-gate__subtitle">Pick how you'd like to explore the demo.</p>
        <div className="landing__buttons">
          <button type="button" className="prejoin__join" onClick={() => navigate("/demo/dashboard")}>
            Try Demo Dashboard with assistant
          </button>
          <button type="button" className="landing__btn-secondary" onClick={() => navigate("/demo/meet")}>
            Get instantly on call for live demo
          </button>
        </div>
        {/* A third, lighter-weight tier — not a demo path, just reference
            material, so it doesn't compete visually with the two CTAs above.
            Public, no visitor gate (see App.tsx's "/docs/*" route). */}
        <button type="button" className="landing__docs-link" onClick={() => navigate("/docs")}>
          Platform Documentation
        </button>
      </div>
    </div>
  );
}
