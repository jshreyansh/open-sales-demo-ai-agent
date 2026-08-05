import { useEffect, useRef, useState } from "react";
import { usePipecatConversation } from "@pipecat-ai/client-react";
import type { ConversationMessagePart } from "@pipecat-ai/client-react";
import { sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import { useVoiceSession } from "../lib/useVoiceSession";
import MeetIcon from "./MeetIcons";

interface ChatWidgetProps {
  currentPage: string;
  onAction: (action: AgentAction) => void;
}

const visitorId = getVisitorId();
const WELCOME = "Hi, I'm Emma. Ask me to show you around — the dashboard, content studio, or brand kit.";

function partText(part: ConversationMessagePart): string {
  if (typeof part.text === "string") return part.text;
  if (part.text && typeof part.text === "object" && "spoken" in part.text) {
    return `${part.text.spoken}${part.text.unspoken}`;
  }
  return "";
}

export default function ChatWidget({ currentPage, onAction }: ChatWidgetProps) {
  const { messages, injectMessage } = usePipecatConversation();
  const { transportState, connecting, isMicEnabled, enableMic, connect, mute } = useVoiceSession(onAction);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [talkMode, setTalkMode] = useState(false);

  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;

  const welcomeSent = useRef(false);
  useEffect(() => {
    if (welcomeSent.current) return;
    welcomeSent.current = true;
    injectMessage({
      role: "assistant",
      parts: [{ text: WELCOME, final: true, createdAt: new Date().toISOString() }],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startTalk() {
    setTalkMode(true);
    try {
      await connect();
    } catch {
      setTalkMode(false);
    }
  }

  function stopTalk() {
    setTalkMode(false);
    mute();
  }

  // Keep in sync if voice was disconnected from elsewhere (e.g. the Meeting
  // Mode hangup button), not just via this widget's own Chat toggle.
  useEffect(() => {
    if (talkMode && transportState === "disconnected") setTalkMode(false);
  }, [talkMode, transportState]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    injectMessage({ role: "user", parts: [{ text, final: true, createdAt: new Date().toISOString() }] });
    setInput("");
    setSending(true);
    try {
      const { reply, action } = await sendMessage(visitorId, text, currentPageRef.current);
      injectMessage({ role: "assistant", parts: [{ text: reply, final: true, createdAt: new Date().toISOString() }] });
      if (action) onAction(action);
    } catch {
      injectMessage({
        role: "assistant",
        parts: [{ text: "Sorry, I couldn't reach the demo backend.", final: true, createdAt: new Date().toISOString() }],
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="chat">
      <div className="chat__header">
        <span>Emma</span>
        <div className="chat__mode-toggle">
          <button
            className={`chat__mode-btn ${!talkMode ? "chat__mode-btn--active" : ""}`}
            onClick={stopTalk}
            disabled={!talkMode}
          >
            Chat
          </button>
          <button
            className={`chat__mode-btn ${talkMode ? "chat__mode-btn--active" : ""}`}
            onClick={startTalk}
            disabled={talkMode || connecting}
          >
            {connecting ? "Connecting…" : "Talk"}
          </button>
          {talkMode && (
            <button
              className="chat__mute-btn"
              onClick={() => enableMic(!isMicEnabled)}
              title={isMicEnabled ? "Mute microphone" : "Unmute microphone"}
            >
              <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} size={14} />
            </button>
          )}
        </div>
      </div>
      <div className="chat__messages">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`chat__message chat__message--${m.role === "user" ? "user" : "agent"}`}
          >
            {m.parts.map((p, j) => (
              <span key={j}>{partText(p)}</span>
            ))}
          </div>
        ))}
      </div>
      <div className="chat__input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder={talkMode ? "Listening… (or type)" : "Ask anything..."}
          disabled={sending}
        />
        <button onClick={handleSend} disabled={sending}>
          Send
        </button>
      </div>
    </div>
  );
}
