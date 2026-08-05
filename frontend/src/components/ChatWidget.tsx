import { useState } from "react";
import { sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";

interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

interface ChatWidgetProps {
  currentPage: string;
  onAction: (action: AgentAction) => void;
}

const visitorId = getVisitorId();

export default function ChatWidget({ currentPage, onAction }: ChatWidgetProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "agent", text: "Hi, I'm Emma. Ask me to show you around — the dashboard, content studio, or brand kit." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const { reply, action } = await sendMessage(visitorId, text, currentPage);
      setMessages((prev) => [...prev, { role: "agent", text: reply }]);
      if (action) onAction(action);
    } catch {
      setMessages((prev) => [...prev, { role: "agent", text: "Sorry, I couldn't reach the demo backend." }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat">
      <div className="chat__header">Emma</div>
      <div className="chat__messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat__message chat__message--${m.role}`}>
            {m.text}
          </div>
        ))}
      </div>
      <div className="chat__input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask anything..."
          disabled={sending}
        />
        <button onClick={handleSend} disabled={sending}>
          Send
        </button>
      </div>
    </div>
  );
}
