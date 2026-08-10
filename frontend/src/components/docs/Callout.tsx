import type { ReactNode } from "react";

interface CalloutProps {
  title?: string;
  type?: "info" | "warn";
  children: ReactNode;
}

// Ported 1:1 from swishx-docs' <Callout> (Fumadocs) — same title/type API,
// so none of the ported .mdx content needed to change.
export default function Callout({ title, type = "info", children }: CalloutProps) {
  return (
    <div className={`docs-callout docs-callout--${type}`}>
      {title && <div className="docs-callout__title">{title}</div>}
      <div className="docs-callout__body">{children}</div>
    </div>
  );
}
