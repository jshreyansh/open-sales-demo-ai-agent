import { useEffect, useRef, useState } from "react";
import { NAV_REGISTRY } from "../registry/pages";
import { getApprovals } from "../lib/api";
import { applyPulse } from "../lib/useHighlight";
import Icon from "./Icon";
import logo from "../assets/contentiq-lockup-light.png";

interface SidebarProps {
  activePageId: string;
  onNavigate: (pageId: string) => void;
}

export default function Sidebar({ activePageId, onNavigate }: SidebarProps) {
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const itemRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  // The active-page CSS class below already tracks activePageId correctly
  // on its own — but a static color swap is easy to miss mid-conversation.
  // This adds the same transient pulse cue every other agent-driven jump
  // gets (ContentStudio's tabs/cards, the wizards' StepBar pills) so a
  // voice-triggered page switch is actually noticeable, not just "quietly
  // now true." Skips the very first mount (no real switch happened yet).
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    applyPulse(itemRefs.current.get(activePageId) ?? null);
  }, [activePageId]);

  useEffect(() => {
    getApprovals()
      .then((data) => setPendingApprovals(data.rows.filter((r) => r.state === "pending").length))
      .catch(() => setPendingApprovals(0));
  }, []);

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--collapsed" : ""}`}>
      <div className="sidebar__top">
        {collapsed ? (
          <span className="sidebar__mark">
            X<Icon name="sparkles" size={9} />
          </span>
        ) : (
          <img src={logo} alt="ContentIQ by swishx" className="sidebar__logo" />
        )}
        <button
          className="sidebar__collapse-btn"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <Icon name="sidebar-collapse" size={13} />
        </button>
      </div>

      <nav className="sidebar__nav">
        {NAV_REGISTRY.map((group) => (
          <div key={group.id} className="sidebar__group">
            {group.label && !collapsed && <div className="sidebar__group-label">{group.label}</div>}
            {group.items.map((item) => {
              const count = item.id === "mlr-review" ? pendingApprovals : 0;
              const indent = item.indent && !collapsed;
              return (
                <button
                  key={item.id}
                  ref={(el) => {
                    if (el) itemRefs.current.set(item.id, el);
                    else itemRefs.current.delete(item.id);
                  }}
                  className={`sidebar__item ${activePageId === item.id ? "sidebar__item--active" : ""} ${indent ? "sidebar__item--indent" : ""}`}
                  disabled={item.status === "soon"}
                  onClick={() => onNavigate(item.id)}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon name={item.icon} size={15} />
                  {!collapsed && <span className="sidebar__item-label">{item.label}</span>}
                  {!collapsed && item.status === "soon" && <span className="sidebar__badge">Soon</span>}
                  {count > 0 && <span className="sidebar__count">{count}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar__bottom">
        <button className="sidebar__item">
          <Icon name="sparkles" size={15} />
          {!collapsed && (
            <span className="sidebar__item-label sidebar__item-label--row">
              Credits <b className="sidebar__credits-value">3,66,998</b>
            </span>
          )}
        </button>
        <button className="sidebar__item">
          <Icon name="settings" size={15} />
          {!collapsed && <span className="sidebar__item-label">Settings</span>}
        </button>
        <div className="sidebar__user">
          <span className="sidebar__avatar">S</span>
          {!collapsed && (
            <div className="sidebar__user-info">
              <span className="sidebar__user-name">Shreyansh</span>
              <span className="sidebar__user-email">shreyansh.jaiswal@swish...</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
