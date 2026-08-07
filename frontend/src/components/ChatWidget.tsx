import { useCallback, useEffect, useRef, useState } from "react";
import { useRTVIClientEvent } from "@pipecat-ai/client-react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import { sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import { useVoiceSession } from "../lib/useVoiceSession";
import MeetIcon from "./MeetIcons";
import Icon from "./Icon";
import { AGENT_NAME, AGENT_PHOTO, AGENT_GREETING } from "../lib/persona";

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
// Kept in sync by hand with backend/src/context/store.py's OPENING_GREETING —
// the voice pipeline speaks that exact text as its first utterance (see
// AgentRuntimeProcessor._greet), so this chat bubble matches what a prospect
// would hear if they switched to Talk mode instead.
const WELCOME = AGENT_GREETING;

let msgSeq = 0;
function nextId() {
  msgSeq += 1;
  return `m${Date.now()}-${msgSeq}`;
}

export default function ChatWidget({ currentPage, onAction }: ChatWidgetProps) {
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

  // The user's side of a voice turn comes through as a real ASR transcript
  // (interim + final chunks, only the final one is a complete utterance).
  // The agent's side doesn't use RTVIEvent.BotTranscript — pipecat only fires
  // that for a streaming LLMTextFrame, and the voice pipeline pushes one
  // complete plain TextFrame instead, so that event never fires here. The
  // agent's reply text arrives via the same voice-reply polling useVoiceSession
  // already does for actions (see the onReply argument below).
  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback(
      (data: { text: string; final: boolean }) => {
        if (data.final) appendMessage("user", data.text);
      },
      [appendMessage]
    )
  );

  const { transportState, connecting, isMicEnabled, enableMic, connect, mute } = useVoiceSession(
    onAction,
    useCallback((text: string) => appendMessage("agent", text), [appendMessage])
  );

  async function startTalk() {
    setTalkMode(true);
    try {
      const connected = await connect();
      if (!connected) {
        // Someone else is already on the line — the voicebot handles one
        // real call at a time (see server.py's _active_call).
        setTalkMode(false);
        appendMessage("agent", `${AGENT_NAME} is already on a call right now. Try again in a few minutes.`);
      }
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
      const { reply, action, lead_in } = await sendMessage(visitorId, text, currentPageRef.current);
      if (action && lead_in) {
        // Same "transition, then action, then explanation" ordering as the
        // voice path: show the lead-in, give it a beat to actually be read,
        // then fire the action and reveal the explanation together — so the
        // reply can talk about what's now on screen instead of what's about
        // to be shown.
        appendMessage("agent", lead_in);
        const leadMs = Math.min(2200, Math.max(500, lead_in.length * 45));
        window.setTimeout(() => {
          onAction(action);
          appendMessage("agent", reply);
        }, leadMs);
      } else {
        appendMessage("agent", reply);
        if (action) {
          // No lead_in (shouldn't normally happen) — approximate reading
          // pace on the full reply as a fallback so the action still doesn't
          // jump the instant the text appears.
          const readMs = Math.min(6000, Math.max(900, reply.length * 45));
          window.setTimeout(() => onAction(action), readMs);
        }
      }
    } catch {
      appendMessage("agent", "Sorry, I couldn't reach the demo backend.");
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <button className="chat-launcher" onClick={() => setOpen(true)} aria-label={`Open chat with ${AGENT_NAME}`}>
        <img src={AGENT_PHOTO} alt="" className="chat-launcher__avatar chat-launcher__avatar--img" />
      </button>
    );
  }

  return (
    <div className={`chat ${expanded ? "chat--expanded" : ""}`}>
      <div className="chat__header">
        <div className="chat__header-title">
          <img src={AGENT_PHOTO} alt="" className="chat__header-avatar chat__header-avatar--img" />
          {AGENT_NAME}
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
