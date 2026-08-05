import { forwardRef, useImperativeHandle, useState } from "react";
import type { ComponentActions } from "./types";

const BrandKitPanel = forwardRef<ComponentActions>((_props, ref) => {
  const [highlighted, setHighlighted] = useState(false);

  useImperativeHandle(ref, () => ({
    highlight: () => {
      setHighlighted(true);
      setTimeout(() => setHighlighted(false), 1500);
    },
    click: () => {},
  }));

  return (
    <div className={`panel ${highlighted ? "panel--highlighted" : ""}`}>
      <h3>Brand Kit</h3>
      <p className="panel__note">Logo, colors, and fonts live here.</p>
    </div>
  );
});

export default BrandKitPanel;
