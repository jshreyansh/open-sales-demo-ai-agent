import { NAV_REGISTRY } from "../registry/pages";

interface SidebarProps {
  activePageId: string;
  onNavigate: (pageId: string) => void;
}

export default function Sidebar({ activePageId, onNavigate }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">Content IQ</div>
      <nav>
        {NAV_REGISTRY.map((group) => (
          <div key={group.id} className="sidebar__group">
            {group.label && <div className="sidebar__group-label">{group.label}</div>}
            {group.items.map((item) => (
              <button
                key={item.id}
                className={`sidebar__item ${activePageId === item.id ? "sidebar__item--active" : ""}`}
                disabled={item.status === "soon"}
                onClick={() => onNavigate(item.id)}
              >
                <span>{item.label}</span>
                {item.status === "soon" && <span className="sidebar__badge">Soon</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
