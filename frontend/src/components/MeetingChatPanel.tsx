import { useEffect, useRef, useState } from "react";
import MeetIcon from "./MeetIcons";

export interface MeetingChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
}

const URL_RE = /(https?:\/\/[^\s]+)/g;

// The one place a message needs to actually be clickable rather than plain
// text — the example gallery's booking link (see MeetingShell.tsx /
// agent_processor.py's _report_chat_message) is a real URL, and a bare
// string isn't tappable/copyable the way a real <a> is.
function renderWithLinks(text: string) {
  // split() with a capturing group always alternates [text, match, text,
  // match, ...] -- odd indices are the captured URLs, even are plain text.
  // Re-testing each part against URL_RE instead would be unreliable: a
  // global-flagged regex's .test() is stateful (tracks lastIndex across
  // calls), which silently skips/misfires on alternating calls.
  const parts = text.split(URL_RE);
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer">
        {part}
      </a>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

interface MeetingChatPanelProps {
  messages: MeetingChatMessage[];
  onSend: (text: string) => void;
  onClose: () => void;
}

// Docked sidebar version of the in-call chat, styled to match Google Meet's
// own "In-call messages" panel. Deliberately not a reuse of ChatWidget.tsx —
// that component is Product Mode's floating/fixed-position launcher and
// isn't meant to be laid out as a flex child inside .meet__body.
export default function MeetingChatPanel({ messages, onSend, onClose }: MeetingChatPanelProps) {
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
      <div className="meet__chat-header">
        <span>In-call messages</span>
        {/* Second way out, matching every real chat panel: the control at
            the bottom toggles it, and this closes it from where your eyes
            already are when you're done reading. */}
        <button className="meet__chat-close" onClick={onClose} aria-label="Close in-call messages">
          <MeetIcon name="close" size={18} />
        </button>
      </div>
      <div className="meet__chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="meet__chat-empty">Messages can only be seen by people in the call</div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`meet__chat-message meet__chat-message--${m.role}`}>
            {renderWithLinks(m.text)}
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
