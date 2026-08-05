import { useEffect, useState } from "react";
import { NAV_REGISTRY } from "../registry/pages";
import { getApprovals } from "../lib/api";
import Icon from "./Icon";

interface SidebarProps {
  activePageId: string;
  onNavigate: (pageId: string) => void;
}

export default function Sidebar({ activePageId, onNavigate }: SidebarProps) {
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const [collapsed, setCollapsed] = useState(false);

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
          <div className="sidebar__brand">
            <span className="sidebar__brand-name">
              Content<span className="sidebar__brand-iq">IQ</span>
              <Icon name="sparkles" size={11} />
            </span>
            <span className="sidebar__brand-sub">
              by swish<span className="sidebar__brand-x">x</span>
            </span>
          </div>
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
            {group.id !== "overview" && <div className="sidebar__divider" />}
            {group.items.map((item) => {
              const count = item.id === "mlr-review" ? pendingApprovals : 0;
              return (
                <button
                  key={item.id}
                  className={`sidebar__item ${activePageId === item.id ? "sidebar__item--active" : ""}`}
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
