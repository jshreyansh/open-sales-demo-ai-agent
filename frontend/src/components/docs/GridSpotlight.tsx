import { useRef, type MouseEvent, type ReactNode } from "react";

interface GridSpotlightProps {
  children: ReactNode;
  className?: string;
}

// Ported from swishx-docs' components/grid-spotlight.tsx — a dot-grid
// texture with a second, brand-orange copy of the same tile revealed only
// inside a soft circle around the cursor (see the --x/--y custom properties
// and .grid-spotlight__glow's radial-gradient mask in index.css). The
// listener has to live on this outermost box, not a background child —
// hit-testing goes to whichever element is topmost at that point regardless
// of visual transparency, so a decorative absolute child behind normal-flow
// content never receives the mousemove itself.
export default function GridSpotlight({ children, className }: GridSpotlightProps) {
  const ref = useRef<HTMLDivElement>(null);

  function onMouseMove(e: MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--x", `${e.clientX - rect.left}px`);
    e.currentTarget.style.setProperty("--y", `${e.clientY - rect.top}px`);
  }

  function onMouseLeave() {
    ref.current?.style.setProperty("--x", "-9999px");
    ref.current?.style.setProperty("--y", "-9999px");
  }

  return (
    <div ref={ref} onMouseMove={onMouseMove} onMouseLeave={onMouseLeave} className={`grid-spotlight ${className || ""}`}>
      <div className="grid-spotlight__base" />
      <div className="grid-spotlight__glow" />
      {children}
    </div>
  );
}
