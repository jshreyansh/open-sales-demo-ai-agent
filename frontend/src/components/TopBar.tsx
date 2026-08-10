import { Link } from "react-router-dom";
import Icon from "./Icon";

export default function TopBar() {
  return (
    <div className="topbar">
      <div className="topbar__search">
        <Icon name="search" size={15} />
        <input placeholder="Search campaigns, content, HCPs..." disabled />
        <span className="topbar__kbd">⌘K</span>
      </div>
      <div className="topbar__right">
        <span className="topbar__demo-pill">
          <span className="topbar__demo-dot" />
          Demo Mode
        </span>
        {/* Public, no visitor gate — see App.tsx's "/docs/*" route. */}
        <Link className="topbar__docs-link" to="/docs">
          <Icon name="book-open" size={14} />
          Documentation
        </Link>
        <button className="topbar__org">
          <span>Roche</span>
          <span className="topbar__org-flag">🇮🇳</span>
          <span className="topbar__org-user">Dushyant</span>
          <Icon name="chevron-down" size={12} />
        </button>
        <button className="topbar__icon-btn">
          <Icon name="bell" size={16} />
        </button>
        <button className="topbar__icon-btn">
          <Icon name="moon" size={16} />
        </button>
      </div>
    </div>
  );
}
