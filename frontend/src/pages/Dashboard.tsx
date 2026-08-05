import { useRef, useState } from "react";
import CreateVideoButton from "../components/CreateVideoButton";
import BrandKitPanel from "../components/BrandKitPanel";
import AnalyticsPanel from "../components/AnalyticsPanel";
import type { ComponentActions } from "../components/types";
import { getVisitorId } from "../lib/session";
import { sendMessage, type AgentAction } from "../lib/api";

interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

const visitorId = getVisitorId();

export default function Dashboard() {
  const createVideoRef = useRef<ComponentActions>(null);
  const brandKitRef = useRef<ComponentActions>(null);
  const analyticsRef = useRef<ComponentActions>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "agent", text: "Hi, I'm Emma. Ask me to show you how to create a video." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  function executeAction(action?: AgentAction) {
    if (!action) return;
    const refByComponent: Record<string, React.RefObject<ComponentActions>> = {
      "create-video": createVideoRef,
      "brand-kit": brandKitRef,
      analytics: analyticsRef,
    };
    const target = refByComponent[action.component]?.current;
    const method = target?.[action.method as keyof ComponentActions];
    if (typeof method === "function") {
      method();
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const { reply, action } = await sendMessage(visitorId, text);
      setMessages((prev) => [...prev, { role: "agent", text: reply }]);
      executeAction(action);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "agent", text: "Sorry, I couldn't reach the demo backend." },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>Dashboard</h1>
      </header>
      <main className="dashboard__grid">
        <CreateVideoButton ref={createVideoRef} />
        <BrandKitPanel ref={brandKitRef} />
        <AnalyticsPanel ref={analyticsRef} />
      </main>

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
    </div>
  );
}
