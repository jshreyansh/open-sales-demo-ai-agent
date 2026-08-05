import { forwardRef, useImperativeHandle, useState } from "react";
import type { ComponentActions } from "./types";

const CreateVideoButton = forwardRef<ComponentActions>((_props, ref) => {
  const [highlighted, setHighlighted] = useState(false);
  const [opened, setOpened] = useState(false);

  useImperativeHandle(ref, () => ({
    highlight: () => {
      setHighlighted(true);
      setTimeout(() => setHighlighted(false), 1500);
    },
    click: () => {
      setOpened(true);
    },
  }));

  return (
    <div className={`panel ${highlighted ? "panel--highlighted" : ""}`}>
      <h3>Create Video</h3>
      <button className="btn-primary">+ Create Video</button>
      {opened && <p className="panel__note">Opening video editor…</p>}
    </div>
  );
});

export default CreateVideoButton;
