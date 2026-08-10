import { Children, useState, type ReactNode } from "react";

interface TabsProps {
  items: string[];
  children: ReactNode;
}

// Ported from swishx-docs' <Tabs>/<Tab> (Fumadocs/@fumadocs/base-ui) — same
// items+value API. Tabs owns the active-index state and picks which child
// Tab's content to show; Tab itself is just a passthrough wrapper.
export function Tabs({ items, children }: TabsProps) {
  const [active, setActive] = useState(0);
  const panels = Children.toArray(children);

  return (
    <div className="docs-tabs">
      <div className="docs-tabs__list" role="tablist">
        {items.map((item, i) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={i === active}
            className={`docs-tabs__tab ${i === active ? "docs-tabs__tab--active" : ""}`}
            onClick={() => setActive(i)}
          >
            {item}
          </button>
        ))}
      </div>
      <div className="docs-tabs__panel">{panels[active]}</div>
    </div>
  );
}

export function Tab({ children }: { value: string; children: ReactNode }) {
  return <>{children}</>;
}
