import { Children, type ReactNode } from "react";

// Ported from swishx-docs' <Steps>/<Step> — a real ordered sequence (the
// reasoning pipeline's six stages), so numbering here is information, not
// decoration. Step itself carries no props; each child's position in the
// list is what determines its number.
export function Steps({ children }: { children: ReactNode }) {
  const items = Children.toArray(children);
  return (
    <div className="docs-steps">
      {items.map((child, i) => (
        <div className="docs-step" key={i}>
          <div className="docs-step__marker">{i + 1}</div>
          <div className="docs-step__body">{child}</div>
        </div>
      ))}
    </div>
  );
}

export function Step({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
