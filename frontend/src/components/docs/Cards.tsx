import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export function Cards({ children }: { children: ReactNode }) {
  return <div className="docs-cards">{children}</div>;
}

interface CardProps {
  title: string;
  href: string;
  description?: string;
}

// href is always an internal /docs/... path in the ported content — routed
// through react-router's Link so it's a real client-side navigation, not a
// full page reload.
export function Card({ title, href, description }: CardProps) {
  return (
    <Link className="docs-card" to={href}>
      <div className="docs-card__title">{title}</div>
      {description && <div className="docs-card__description">{description}</div>}
    </Link>
  );
}
