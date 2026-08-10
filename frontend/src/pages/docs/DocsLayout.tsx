import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { DOCS_NAV, type DocsNavNode } from "./nav";
import DocsHeader from "../../components/docs/DocsHeader";
import Icon from "../../components/Icon";

function subtreeContainsSlug(node: DocsNavNode, slug: string): boolean {
  if (node.type === "page") return node.slug === slug;
  return node.items.some((item) => subtreeContainsSlug(item, slug));
}

interface NavNodeProps {
  node: DocsNavNode;
  closedGroups: Set<string>;
  toggleGroup: (title: string) => void;
  onNavigate?: () => void;
}

function NavNode({ node, closedGroups, toggleGroup, onNavigate }: NavNodeProps) {
  if (node.type === "page") {
    return (
      <NavLink
        to={`/docs/api/${node.slug}`}
        onClick={onNavigate}
        className={({ isActive }) => `docs-nav__link ${isActive ? "docs-nav__link--active" : ""}`}
      >
        {node.title}
      </NavLink>
    );
  }
  const isOpen = !closedGroups.has(node.title);
  return (
    <div className="docs-nav__group">
      <button type="button" className="docs-nav__group-title" onClick={() => toggleGroup(node.title)} aria-expanded={isOpen}>
        <span>{node.title}</span>
        <Icon name="chevron-down" size={13} className={`docs-nav__chevron ${isOpen ? "docs-nav__chevron--open" : ""}`} />
      </button>
      {isOpen && (
        <div className="docs-nav__group-items">
          {node.items.map((item) => (
            <NavNode
              key={item.type === "page" ? item.slug : item.title}
              node={item}
              closedGroups={closedGroups}
              toggleGroup={toggleGroup}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Default state is everything expanded (matching swishx-docs' own
// `defaultOpenLevel: Infinity`) — closedGroups tracks exceptions to that,
// not the other way round. Navigating to a page force-reopens whichever
// group(s) contain it, in case the visitor had collapsed one and then
// followed a link (from the TOC, a card, etc.) into it.
function useDocsNavState(activeSlug: string) {
  const [closedGroups, setClosedGroups] = useState<Set<string>>(new Set());

  useEffect(() => {
    setClosedGroups((prev) => {
      let changed = false;
      const next = new Set(prev);
      function open(nodes: DocsNavNode[]) {
        for (const node of nodes) {
          if (node.type === "group" && subtreeContainsSlug(node, activeSlug)) {
            if (next.delete(node.title)) changed = true;
            open(node.items);
          }
        }
      }
      open(DOCS_NAV);
      return changed ? next : prev;
    });
  }, [activeSlug]);

  function toggleGroup(title: string) {
    setClosedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  }

  return { closedGroups, toggleGroup };
}

interface DocsLayoutProps {
  children: ReactNode;
  toc?: ReactNode;
  activeSlug: string;
}

// The docs' own shell — deliberately separate from the product's
// Sidebar/TopBar (components/Sidebar.tsx, components/TopBar.tsx), which are
// specific to the gated dashboard. Docs are public, so this never renders
// inside a gate.
export default function DocsLayout({ children, toc, activeSlug }: DocsLayoutProps) {
  const { closedGroups, toggleGroup } = useDocsNavState(activeSlug);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // A route change (clicking a link) should close the mobile drawer, same
  // as any real app's mobile nav — without this, "navigate" from the drawer
  // would leave it covering the new page.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [activeSlug]);

  return (
    <div className="docs-layout">
      <DocsHeader onToggleSidebar={() => setMobileNavOpen((v) => !v)} />
      <div className="docs-layout__body">
        {mobileNavOpen && <div className="docs-sidebar-overlay" onClick={() => setMobileNavOpen(false)} />}
        <nav className={`docs-sidebar ${mobileNavOpen ? "docs-sidebar--mobile-open" : ""}`}>
          <div className="docs-sidebar__nav">
            {DOCS_NAV.map((node) => (
              <NavNode
                key={node.type === "page" ? node.slug : node.title}
                node={node}
                closedGroups={closedGroups}
                toggleGroup={toggleGroup}
                onNavigate={() => setMobileNavOpen(false)}
              />
            ))}
          </div>
        </nav>
        <main className="docs-content">
          <div className="docs-content__inner">{children}</div>
        </main>
        {toc && <aside className="docs-toc-col">{toc}</aside>}
      </div>
    </div>
  );
}
