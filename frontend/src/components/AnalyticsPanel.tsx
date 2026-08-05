import { forwardRef, useImperativeHandle, useState } from "react";
import type { ComponentActions } from "./types";

const AnalyticsPanel = forwardRef<ComponentActions>((_props, ref) => {
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
      <h3>Analytics</h3>
      <p className="panel__note">Views, engagement, and reach.</p>
    </div>
  );
});

export default AnalyticsPanel;
