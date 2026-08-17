import { useEffect, useRef, useState } from "react";
import MeetIcon from "./MeetIcons";

export interface MeetingChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
}

interface MeetingChatPanelProps {
  messages: MeetingChatMessage[];
  onSend: (text: string) => void;
}

// Docked sidebar version of the in-call chat, styled to match Google Meet's
// own "In-call messages" panel. Deliberately not a reuse of ChatWidget.tsx —
// that component is Product Mode's floating/fixed-position launcher and
// isn't meant to be laid out as a flex child inside .meet__body.
export default function MeetingChatPanel({ messages, onSend }: MeetingChatPanelProps) {
  const [input, setInput] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    onSend(text);
    setInput("");
  }

  return (
    <div className="meet__chat-panel">
      <div className="meet__chat-header">In-call messages</div>
      <div className="meet__chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="meet__chat-empty">Messages can only be seen by people in the call</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`meet__chat-message meet__chat-message--${m.role}`}>
            {m.text}
          </div>
        ))}
      </div>
      <div className="meet__chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Send a message"
        />
        <button onClick={handleSend} aria-label="Send message">
          <MeetIcon name="send" size={16} />
        </button>
      </div>
    </div>
  );
}
