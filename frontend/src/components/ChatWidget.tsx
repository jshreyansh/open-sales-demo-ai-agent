import { useEffect, useRef, useState } from "react";
import {
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  usePipecatConversation,
} from "@pipecat-ai/client-react";
import type { ConversationMessagePart } from "@pipecat-ai/client-react";
import { getVoiceAction, sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import { connectVoice } from "../lib/pipecatClient";
import MeetIcon from "./MeetIcons";

interface ChatWidgetProps {
  currentPage: string;
  onAction: (action: AgentAction) => void;
  /** Meeting Mode: connect voice immediately on mount, no manual toggle. */
  autoConnectVoice?: boolean;
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

export default function ChatWidget({ currentPage, onAction, autoConnectVoice }: ChatWidgetProps) {
  const { messages, injectMessage } = usePipecatConversation();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const transportState = usePipecatClientTransportState();
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [talkMode, setTalkMode] = useState(false);

  const connecting = transportState === "connecting" || transportState === "authenticating" || transportState === "initializing";
  const voiceConnected = transportState === "connected" || transportState === "ready";

  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;
  const onActionRef = useRef(onAction);
  onActionRef.current = onAction;

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
    // Connect only once — reconnecting fires the client library's own
    // "Connected" handler, which wipes the whole conversation history as a
    // side effect. After the first connection, switching modes is just a
    // mute/unmute so the shared transcript survives toggling back and forth.
    if (transportState === "disconnected") {
      try {
        await connectVoice(visitorId);
      } catch {
        setTalkMode(false);
        return;
      }
    }
    enableMic(true);
  }

  function stopTalk() {
    setTalkMode(false);
    enableMic(false);
  }

  useEffect(() => {
    if (autoConnectVoice) startTalk();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnectVoice]);

  // Keep in sync if voice was disconnected from elsewhere (e.g. the Meeting
  // Mode hangup button), not just via this widget's own Chat toggle.
  useEffect(() => {
    if (talkMode && transportState === "disconnected") setTalkMode(false);
  }, [talkMode, transportState]);

  // Voice-triggered UI actions arrive out-of-band (the voice process is a
  // separate service from this REST API) — poll while a call is active.
  useEffect(() => {
    if (!voiceConnected) return;
    const id = setInterval(async () => {
      const action = await getVoiceAction(visitorId).catch(() => null);
      if (action) onActionRef.current(action);
    }, 800);
    return () => clearInterval(id);
  }, [voiceConnected]);

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
