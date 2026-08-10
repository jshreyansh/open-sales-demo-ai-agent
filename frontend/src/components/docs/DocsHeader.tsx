import { Link } from "react-router-dom";
import SwishXMark from "./SwishXMark";
import Icon from "../Icon";

// Same mark the original swishx-docs site rendered for its (non-clickable)
// GitHub link — ported for visual parity, still not a real link since there
// isn't a public repo for this project to point it at.
function GithubMark() {
  return (
    <svg role="img" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

interface DocsHeaderProps {
  // Only passed by DocsLayout (the API-reference content shell) — the hub
  // page (DocsHome) has no sidebar to toggle.
  onToggleSidebar?: () => void;
}

// Shared between DocsHome (the hub at /docs) and DocsLayout (the content
// shell at /docs/api/*) so the brand/nav treatment is identical everywhere
// in the docs, matching swishx-docs' own layout.shared.tsx baseOptions().
export default function DocsHeader({ onToggleSidebar }: DocsHeaderProps) {
  return (
    <header className="docs-header">
      <div className="docs-header__left">
        {onToggleSidebar && (
          <button type="button" className="docs-header__menu-btn" onClick={onToggleSidebar} aria-label="Toggle navigation">
            <Icon name="menu" size={18} />
          </button>
        )}
        <Link to="/docs" className="docs-header__brand">
          <span className="docs-header__mark">
            <SwishXMark size={18} />
          </span>
          <span className="docs-header__brand-name">SwishX</span>
          <span className="docs-header__brand-sub">Knowledge Base</span>
        </Link>
      </div>
      <div className="docs-header__right">
        <div className="docs-header__search" title="Search (not wired up yet)">
          <Icon name="search" size={14} />
          <span>Search</span>
          <span className="docs-header__kbd">⌘K</span>
        </div>
        <a className="docs-header__nav-link" href="https://swishx-api-platform.vercel.app" target="_blank" rel="noopener noreferrer">
          API Platform
        </a>
        <a className="docs-header__nav-link" href="https://swishx.com" target="_blank" rel="noopener noreferrer">
          swishx.com
        </a>
        <button type="button" className="docs-header__icon-btn" aria-label="Toggle theme" title="Not wired up yet">
          <Icon name="moon" size={16} />
        </button>
        <span className="docs-header__icon-btn docs-header__icon-btn--static">
          <GithubMark />
        </span>
      </div>
    </header>
  );
}
