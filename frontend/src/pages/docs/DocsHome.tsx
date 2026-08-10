import { Link } from "react-router-dom";
import DocsHeader from "../../components/docs/DocsHeader";
import GridSpotlight from "../../components/docs/GridSpotlight";
import SwishXMark from "../../components/docs/SwishXMark";

// The Knowledge Base hub at /docs — ported from swishx-docs' own
// app/(home)/page.tsx. Only one card is live today (API Reference, ->
// /docs/api); Product Documentation is a real, named next step (per
// Dushyant's feedback — see backend/src/agent/knowledge's gap) rather than
// something invented for this page, so it's shown disabled/"Soon" rather
// than omitted.
export default function DocsHome() {
  return (
    <div className="docs-home">
      <DocsHeader />
      <GridSpotlight className="docs-home__hero">
        <span className="docs-home__pill">
          <span className="docs-home__pill-mark">
            <SwishXMark size={13} />
          </span>
          Docs
        </span>
        <h1 className="docs-home__title">SwishX Knowledge Base</h1>
        <p className="docs-home__subtitle">
          API documentation for building on SwishX — endpoints, authentication, and the request lifecycle.
        </p>

        <div className="docs-home__cards">
          <Link to="/docs/api" className="docs-home__card">
            <p className="docs-home__card-title">API Reference</p>
            <p className="docs-home__card-desc">Endpoints, authentication, and the reasoning pipeline.</p>
          </Link>
          <div className="docs-home__card docs-home__card--soon" aria-disabled="true">
            <p className="docs-home__card-title">
              Product Documentation <span className="docs-home__soon-badge">Soon</span>
            </p>
            <p className="docs-home__card-desc">Using ContentIQ itself — coming next.</p>
          </div>
        </div>
      </GridSpotlight>

      <footer className="docs-home__footer">
        &copy; {new Date().getFullYear()} SwishX ·{" "}
        <a href="https://swishx.com" target="_blank" rel="noopener noreferrer">
          swishx.com
        </a>{" "}
        ·{" "}
        <a href="https://swishx-api-platform.vercel.app" target="_blank" rel="noopener noreferrer">
          API Platform
        </a>
      </footer>
    </div>
  );
}
