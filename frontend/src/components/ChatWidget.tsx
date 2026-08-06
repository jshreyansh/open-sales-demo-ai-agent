import { useCallback, useEffect, useRef, useState } from "react";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import { useVoiceSession } from "../lib/useVoiceSession";
import MeetIcon from "./MeetIcons";
import Icon from "./Icon";

interface ChatWidgetProps {
  currentPage: string;
  onAction: (action: AgentAction) => void;
}

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
}

const visitorId = getVisitorId();
const WELCOME = "Hi, I'm Emma. Ask me to show you around — the dashboard, content studio, or brand kit.";

let msgSeq = 0;
function nextId() {
  msgSeq += 1;
  return `m${Date.now()}-${msgSeq}`;
}

export default function ChatWidget({ currentPage, onAction }: ChatWidgetProps) {
  const { transportState, connecting, isMicEnabled, enableMic, connect, mute } = useVoiceSession(onAction);
  // A plain local list — exactly one bubble per turn. Pipecat's own
  // conversation aggregation (meant for merging streamed ASR/LLM chunks into
  // one utterance) was merging separate user sends into a single bubble, so
  // we don't use it as the render source at all; RTVI transcript events feed
  // straight into this list instead.
  const [messages, setMessages] = useState<ChatMessage[]>([{ id: "welcome", role: "agent", text: WELCOME }]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [talkMode, setTalkMode] = useState(false);
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;

  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, open, sending]);

  const appendMessage = useCallback((role: ChatMessage["role"], text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { id: nextId(), role, text }]);
  }, []);

  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback(
      (data: { text: string; final: boolean }) => {
        if (data.final) appendMessage("user", data.text);
      },
      [appendMessage]
    )
  );
  useRTVIClientEvent(
    RTVIEvent.BotTranscript,
    // Unlike UserTranscript (interim + final ASR chunks), BotTranscript only
    // fires once per complete generated utterance — no final flag to check.
    useCallback(
      (data: { text: string }) => {
        appendMessage("agent", data.text);
      },
      [appendMessage]
    )
  );

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
    appendMessage("user", text);
    setInput("");
    setSending(true);
    try {
      const { reply, action } = await sendMessage(visitorId, text, currentPageRef.current);
      appendMessage("agent", reply);
      if (action) {
        // There's no real speech to sync to in typed chat, so approximate
        // reading pace instead — the reply is fully explained by the time
        // the action lands, rather than the screen jumping the instant the
        // text appears.
        const readMs = Math.min(6000, Math.max(900, reply.length * 45));
        window.setTimeout(() => onAction(action), readMs);
      }
    } catch {
      appendMessage("agent", "Sorry, I couldn't reach the demo backend.");
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button className="chat-launcher" onClick={() => setOpen(true)} aria-label="Open chat with Emma">
        <span className="chat-launcher__avatar">E</span>
      </button>
    );
  }

  return (
    <div className={`chat ${expanded ? "chat--expanded" : ""}`}>
      <div className="chat__header">
        <div className="chat__header-title">
          <span className="chat__header-avatar">E</span>
          Emma
        </div>
        <div className="chat__header-actions">
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
          </div>
          {talkMode && (
            <button
              className="chat__icon-btn"
              onClick={() => enableMic(!isMicEnabled)}
              title={isMicEnabled ? "Mute microphone" : "Unmute microphone"}
            >
              <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} size={14} />
            </button>
          )}
          <button
            className="chat__icon-btn"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "Restore" : "Expand"}
          >
            <Icon name={expanded ? "collapse" : "expand"} size={14} />
          </button>
          <button className="chat__icon-btn" onClick={() => setOpen(false)} title="Minimize">
            <Icon name="chevron-down" size={16} />
          </button>
        </div>
      </div>

      <div className="chat__messages" ref={listRef}>
        {messages.map((m) => (
          <div key={m.id} className={`chat__message chat__message--${m.role}`}>
            {m.text}
          </div>
        ))}
        {sending && (
          <div className="chat__message chat__message--agent chat__message--typing">
            <span className="chat__typing-dot" />
            <span className="chat__typing-dot" />
            <span className="chat__typing-dot" />
          </div>
        )}
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
