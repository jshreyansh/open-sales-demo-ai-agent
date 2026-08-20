import { useCallback, useEffect, useRef, useState } from "react";
import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import { useVoiceSession } from "../lib/useVoiceSession";
import { useAudioLevelRing } from "../lib/useAudioLevelRing";
import { useReportedAudioLevelRing } from "../lib/useReportedAudioLevelRing";
import { useFlipTiles } from "../lib/useFlipTiles";
import { useLocalCamera } from "../lib/useLocalCamera";
import { claimVoiceLock, sendMeetingChatMessage, setHandRaiseState, startSession, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import { useRegisterComponent } from "../lib/uiRegistry";
import MeetIcon from "./MeetIcons";
import Icon from "./Icon";
import PreJoinScreen from "./PreJoinScreen";
import MeetingChatPanel, { type MeetingChatMessage } from "./MeetingChatPanel";
import ExampleGalleryPanel from "./ExampleGalleryPanel";
import { AGENT_NAME, AGENT_INITIAL, AGENT_PHOTO } from "../lib/persona";
import { playJoinSound, playMessageSound, primeSounds } from "../lib/sounds";

const visitorId = getVisitorId();

// Same destination the agent sends into the chat panel when it opens the
// showcase (backend: agent_processor.py's BOOKING_LINK_URL). Duplicated here
// rather than fetched, since the "Talk to the team" control has to work even
// if the voice pipeline is down — keep the two in sync if it ever changes.
const BOOKING_LINK_URL = "https://www.swishx.com/calendar";

// The overflow menu's destinations. Every one opens in a NEW TAB — the call
// is live in this one, and navigating away from it would drop the visitor
// mid-conversation. /docs is same-origin so it's built off window.origin
// rather than hardcoded, which keeps it correct on localhost and in prod.
const MORE_MENU_LINKS: { id: string; icon: "docs" | "calendar" | "linkedin" | "x"; label: string; href: string }[] = [
  { id: "docs", icon: "docs", label: "Platform Documentation", href: "/docs" },
  { id: "ceo", icon: "calendar", label: "Talk to CEO", href: BOOKING_LINK_URL },
  { id: "linkedin", icon: "linkedin", label: "Visit LinkedIn", href: "https://www.linkedin.com/company/swishx/" },
  { id: "x", icon: "x", label: "Follow on X", href: "https://x.com/SwishX_hq" },
];

let chatMsgSeq = 0;
function nextChatMsgId() {
  chatMsgSeq += 1;
  return `mc${Date.now()}-${chatMsgSeq}`;
}

interface MeetingShellProps {
  children: React.ReactNode;
  onLeave: () => void;
  onAction: (action: AgentAction) => void;
}

const MEETING_CODE = "demo-call-pnx";
const JOIN_COUNTDOWN_SECS = 5;
// A quick double-click/double-tap on the hand-raise button toggled
// raise->lower->raise within a second or two, which the backend correctly
// reads as two genuine, separate raises (each deserving its own spoken
// handoff) — reading, from the visitor's side, as the agent repeating
// itself for what looked like one click. This is purely a debounce against
// that accidental double-toggle, not a rate limit on genuine re-raises.
const HAND_RAISE_DEBOUNCE_MS = 800;
// Fiona starts presenting shortly after she arrives — she's mid-greeting by
// then, which is exactly when a real rep would say "let me share my screen".
// Not tied to her first UI action any more: that could be many seconds later
// (or never, if the prospect just wants to talk), leaving the call sitting on
// two idle tiles.
const SHARE_START_AFTER_JOIN_MS = 2500;
// How long the "starting to present" loader holds before the app is revealed.
// Mirrors the real handshake delay every conferencing tool shows, which is
// what makes the share read as something happening rather than a page swap.
const SHARE_LOADER_MS = 2000;

// "Shreyansh Jaiswal" -> "SJ", "Shreyansh" -> "S". Falls back to "Y" (for
// "You") only while we genuinely don't have a name yet — the gate always
// collects one, so in practice the real initials are known from the moment
// the visitor lands in the room.
function initialsFrom(name?: string): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "Y";
  const letters = parts.slice(0, 2).map((p) => p[0]).join("");
  return letters.toUpperCase();
}

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000 * 30);
    return () => clearInterval(id);
  }, []);
  return now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// The box-shadow (edge stroke + soft glow) is driven by whichever ring
// source the caller passes in — useAudioLevelRing off a real audio track
// for "You" (the visitor's own mic), useReportedAudioLevelRing off the
// backend's server-computed loudness for the agent (its synthesized speech
// has no MediaStreamTrack to analyse under WebSocketTransport, see that
// hook's docstring). Not a fixed pulse animation either way, so it only
// shows when they're actually making sound. Set on the avatar circle
// itself, not a separate larger ring element with a gap.
function TileAvatar({
  ringRef,
  photo,
  letter,
  avatarClassName,
}: {
  ringRef: React.RefObject<HTMLDivElement>;
  photo?: string;
  letter: string;
  avatarClassName: string;
}) {
  return (
    <div className={`meet__avatar ${avatarClassName}`} ref={ringRef}>
      {photo ? <img src={photo} alt="" className="meet__avatar-img" /> : letter}
    </div>
  );
}

export default function MeetingShell({ children, onLeave, onAction }: MeetingShellProps) {
  const time = useClock();
  const [handRaised, setHandRaised] = useState(false);
  const [countdown, setCountdown] = useState(JOIN_COUNTDOWN_SECS);
  // Gates the join countdown (and, transitively, the voice connect effect
  // below) behind PreJoinScreen — the visitor picks a rep and gives their
  // name there first, a real call doesn't auto-connect before that.
  const [joined, setJoined] = useState(false);
  // Captured from PreJoinScreen — threaded into connect() below so the
  // voice pipeline's own process (see the connect-effect's comment) gets it
  // directly, rather than relying on a side channel it can't see.
  const [visitorName, setVisitorName] = useState<string | undefined>(undefined);
  const [visitorCompany, setVisitorCompany] = useState<string | undefined>(undefined);
  const [visitorEmail, setVisitorEmail] = useState<string | undefined>(undefined);
  // In-call text chat — mirrors Google Meet's own panel: only the typed
  // exchanges live here, not a running transcript of the whole spoken call
  // (see the onReply filter below, which drops anything not explicitly
  // tagged source: "chat").
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<MeetingChatMessage[]>([]);
  // The one meeting-chrome surface a visitor can actually touch themselves
  // (see ExampleGalleryPanel's docstring) — opened by the agent (registered
  // under a fixed "meeting" pseudo-page, not any particular product page,
  // since this can be asked for from anywhere) rather than a control button,
  // matching runtime.py's instruction 13.
  const [galleryOpen, setGalleryOpen] = useState(false);
  // Unread in-call messages, shown as a dot on the chat control. Counts only
  // while the panel is CLOSED; opening it is what marks them read, the same
  // way every messaging UI behaves.
  const [unreadChat, setUnreadChat] = useState(0);
  // The agent has actually "entered the room". Distinct from voiceConnected:
  // the visitor is in the meeting alone first (their own tile, no agent tile,
  // nothing shared), and the agent appears a beat later — which is what a
  // real call looks like, and what makes the greeting land as someone
  // arriving rather than as a page that was already loaded.
  const [agentJoined, setAgentJoined] = useState(false);
  // Screen share starts on the agent's FIRST real UI action, not on join.
  // She greets and offers a walkthrough with nothing shared; the share
  // begins at the exact moment there's something to show. Using the action
  // itself as the trigger keeps that honest — the screen appears because
  // she's driving it, not on a timer pretending to.
  const [screenShareActive, setScreenShareActive] = useState(false);
  // "connecting" while the loader is up, "live" once the app is revealed.
  // Separate from screenShareActive because the layout starts moving (tiles
  // to the right, stage opening) at the START of the share, while the content
  // itself only appears at the end of the loader.
  const [sharePhase, setSharePhase] = useState<"idle" | "connecting" | "live">("idle");
  // Set when the agent asks to open the booking portal — see the
  // "booking-portal" registry action below.
  const [bookingPrompt, setBookingPrompt] = useState(false);
  // Real self-view. The stream is local-only — attached to a <video> in the
  // You tile and never added to the peer connection, never recorded, never
  // uploaded (see useLocalCamera). The agent is still a photo; only the
  // visitor's own tile goes live.
  const [cameraOn, setCameraOn] = useState(false);
  const { stream: cameraStream, status: cameraStatus } = useLocalCamera(cameraOn);
  const selfVideoRef = useRef<HTMLVideoElement | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);

  // srcObject can't be set through JSX, so it's assigned imperatively
  // whenever either the element or the stream changes.
  useEffect(() => {
    const el = selfVideoRef.current;
    if (!el) return;
    el.srcObject = cameraStream;
    if (cameraStream) el.play().catch(() => {/* autoplay guard; muted so this is rare */});
  }, [cameraStream]);

  // If the browser denied the camera (or there isn't one), snap the control
  // back off rather than leaving it lit over an empty tile.
  useEffect(() => {
    if (cameraStatus === "denied" || cameraStatus === "unavailable") setCameraOn(false);
  }, [cameraStatus]);

  // One string identifying the current tile layout. Every distinct value is
  // a different grid shape, so it's exactly what the FLIP pass keys on.
  const layoutKey =
    (screenShareActive ? "sharing" : agentJoined ? "duo" : "solo") + (chatOpen ? "-chat" : "");
  const mainRef = useRef<HTMLDivElement>(null);
  useFlipTiles(mainRef, layoutKey);

  const handleAgentAction = useCallback(
    (action: AgentAction) => {
      // Only real product navigation starts the share. The "meeting" page is
      // a pseudo-page for call chrome (the example gallery, the booking tab)
      // — firing one of those must not put a dashboard on screen that the
      // agent never actually walked anyone to. Caught in testing: opening the
      // booking portal was starting the screen share by itself.
      // An early real navigation still starts the share immediately rather
      // than waiting out the timer below — whichever comes first.
      if (action.page !== "meeting") setScreenShareActive(true);
      onAction(action);
    },
    [onAction],
  );

  useRegisterComponent("meeting", "example-gallery", {
    open: () => setGalleryOpen(true),
  });
  // Opening a tab from a WebSocket-driven agent action is not a user
  // gesture, so browsers block window.open() outright. Rather than fail
  // silently we try it, and fall back to a card the visitor clicks — that
  // click IS a gesture, so the tab always opens one way or the other.
  useRegisterComponent("meeting", "booking-portal", {
    open: () => {
      const w = window.open(BOOKING_LINK_URL, "_blank", "noopener,noreferrer");
      if (!w) setBookingPrompt(true);
    },
  });
  const chatOpenRef = useRef(false);
  chatOpenRef.current = chatOpen;
  const handleChatReply = useCallback((text: string, source: "voice" | "chat") => {
    if (source !== "chat") return;
    setChatMessages((prev) => [...prev, { id: nextChatMsgId(), role: "agent", text }]);
    playMessageSound();
    // Read via ref, not the state value: this callback is memoised with an
    // empty dep list (it's handed to useVoiceSession once), so closing over
    // `chatOpen` directly would freeze it at its first value and the badge
    // would keep counting even with the panel open.
    if (!chatOpenRef.current) setUnreadChat((n) => n + 1);
  }, []);
  const { voiceConnected, isMicEnabled, enableMic, connect, mute, isUserSpeaking, isAgentSpeaking } = useVoiceSession(handleAgentAction, handleChatReply);

  function handleSendChat(text: string) {
    setChatMessages((prev) => [...prev, { id: nextChatMsgId(), role: "user", text }]);
    void sendMeetingChatMessage(visitorId, text);
  }
  // "You" tile: real local mic MediaStreamTrack, analysed client-side. The
  // agent's tile: WebSocketTransport exposes no "bot" track at all (its
  // audio never becomes an inspectable MediaStreamTrack), so its ring is
  // driven by real server-computed loudness reported over RTVI instead —
  // see useReportedAudioLevelRing's docstring. Neither is the same as
  // isUserSpeaking/isAgentSpeaking (those are VAD start/stop booleans).
  const localAudioTrack = usePipecatClientMediaTrack("audio", "local");
  const youRingRef = useAudioLevelRing(localAudioTrack);
  const agentRingRef = useReportedAudioLevelRing();

  // The agent "joins" only after the countdown finishes, which itself only
  // starts once the visitor has actually picked a rep and given their name
  // on PreJoinScreen — a real call doesn't connect the instant the tab
  // loads, it shows the join intro first.
  useEffect(() => {
    if (!joined) return;
    if (countdown <= 0) return;
    const id = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [joined, countdown]);

  // The visitor is in the room the instant they click Join — alone, with
  // their own chime, exactly like every real conferencing product. The
  // agent's arrival is a separate, later event with its own chime.
  useEffect(() => {
    if (!joined) return;
    playJoinSound();
  }, [joined]);

  // The agent "arrives" once her voice connection is actually up — a real
  // event, not a timer. The countdown above still paces the connect itself,
  // so in practice this lands a beat after the visitor's own join, which is
  // the effect we want: you're in first, she follows.
  useEffect(() => {
    if (!voiceConnected || agentJoined) return;
    setAgentJoined(true);
    playJoinSound();
  }, [voiceConnected, agentJoined]);

  // She joins, greets, and starts presenting a couple of seconds later — the
  // share is driven off her arrival, not off whatever she happens to click.
  useEffect(() => {
    if (!agentJoined || screenShareActive) return;
    const id = setTimeout(() => setScreenShareActive(true), SHARE_START_AFTER_JOIN_MS);
    return () => clearTimeout(id);
  }, [agentJoined, screenShareActive]);

  // Two beats to the share: the layout reflows and the loader shows
  // ("connecting"), then the app is revealed ("live").
  useEffect(() => {
    if (!screenShareActive) return;
    setSharePhase("connecting");
    const id = setTimeout(() => setSharePhase("live"), SHARE_LOADER_MS);
    return () => clearTimeout(id);
  }, [screenShareActive]);

  // This is the only place that triggers the voice connection in Meeting
  // Mode — a real call auto-joins, it isn't a button the visitor clicks.
  // connect() itself enables the mic (that's the right default for Product
  // Mode's explicit "Talk" button) — Meeting Mode wants the opposite default,
  // muted until the visitor deliberately unmutes, so mute right after.
  //
  // visitorName is passed straight into connect() (which threads it onto
  // the WebSocket URL as a query param, see pipecatClient.ts) rather than
  // relying on the earlier POST /api/session/start alone — that REST call
  // lands in the REST API process (server.py, port 8787), a completely
  // separate OS process from the voice pipeline it needs to reach (bot.py,
  // port 7860), each with its own independent in-memory session store. Only
  // what actually reaches bot.py's own process affects what it speaks.
  const connectStarted = useRef(false);
  useEffect(() => {
    if (!joined) return;
    if (countdown > 0) return;
    if (connectStarted.current) return;
    connectStarted.current = true;
    void connect(visitorName, visitorCompany, visitorEmail).then(() => mute());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, countdown]);

  // The backend can end a call on its own now (see agent_processor.py's
  // idle-timeout watcher — someone who mutes and walks away without
  // hanging up), not just the visitor clicking hangup. Without this, that
  // would leave the visitor sitting on the "Our agent is joining..." banner
  // for a call that's actually already over, which reads as a bug rather
  // than an intentional end. Once the call has genuinely connected, a drop
  // back to disconnected is treated the same as clicking hangup.
  const wasConnected = useRef(false);
  useEffect(() => {
    if (voiceConnected) {
      wasConnected.current = true;
      return;
    }
    if (wasConnected.current) {
      wasConnected.current = false;
      onLeave();
    }
  }, [voiceConnected, onLeave]);

  // The overflow menu closes the way every real menu does: the same button
  // toggles it, Escape dismisses it, and a click anywhere outside closes it.
  // The trigger is excluded from the outside-click check via its own class,
  // otherwise the toggle and this handler would fight and it'd never open.
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!moreOpen) return;
    function onDown(e: MouseEvent) {
      const t = e.target as HTMLElement | null;
      if (moreRef.current?.contains(t as Node)) return;
      if (t?.closest?.(".meet__ctrl--more")) return;
      setMoreOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMoreOpen(false);
    }
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [moreOpen]);

  // Spacebar toggles mute, same convention as Google Meet/Zoom — but only
  // once actually connected, and never while focus is in a text field (the
  // in-call chat input below, or the chat input rendered in `children`),
  // where a space is just a space.
  useEffect(() => {
    if (!voiceConnected) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      e.preventDefault();
      enableMic(!isMicEnabled);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [voiceConnected, isMicEnabled, enableMic]);

  // A real toggle, not a momentary press: the visitor raises their hand and
  // it stays raised — same as actually raising a hand in a room — until they
  // click it again to lower it. Nothing auto-resets this; the agent hands
  // off once (see agent_processor.py's _hand_ack_sent) but never lowers the
  // hand itself, since only the visitor really knows when their question's
  // been answered.
  const lastHandRaiseToggle = useRef(0);
  function handleToggleHandRaise() {
    const now = Date.now();
    if (now - lastHandRaiseToggle.current < HAND_RAISE_DEBOUNCE_MS) return;
    lastHandRaiseToggle.current = now;
    const next = !handRaised;
    setHandRaised(next);
    void setHandRaiseState(visitorId, next);
  }

  // Claimed here, at the moment of clicking Join, not later when connect()
  // actually opens the WebSocket after the countdown — reserving the slot
  // immediately (rather than leaving a 5-second window where a second
  // visitor could also slip through the countdown) is what PreJoinScreen's
  // busy message is actually protecting. connect() below claims again for
  // the same visitor when it runs, which is a harmless no-op re-claim, not
  // a second real check.
  //
  // The actual voice personalization happens via connect(visitorName) in
  // the effect above. startSession here is a separate, secondary thing: it
  // seeds the REST API process's own session store with the same name, in
  // case anything reads it from that side later — which now includes the
  // in-call chat panel's messages, routed through the REST API's mailbox.
  async function handleJoin(name: string, company: string, email: string): Promise<boolean> {
    // Runs inside the click handler — the one guaranteed user gesture — so
    // the audio elements are unlocked before any chime needs to play.
    primeSounds();
    const claimed = await claimVoiceLock(visitorId);
    if (!claimed) return false;
    void startSession(visitorId, name, company, email);
    setVisitorName(name);
    setVisitorCompany(company);
    setVisitorEmail(email);
    setJoined(true);
    return true;
  }

  if (!joined) {
    return <PreJoinScreen onJoin={handleJoin} />;
  }

  return (
    <div className="meet">
      <div className="meet__topbar">
        <div className="meet__topbar-left">
          <span>{time}</span>
          <span className="meet__dot">|</span>
          <span>{MEETING_CODE}</span>
          <MeetIcon name="info" size={15} />
        </div>
        <div className="meet__topbar-right">
          {sharePhase === "live" && (
            <span className="meet__presenting">
              <span className="meet__avatar meet__avatar--tiny meet__avatar--tiny-agent">
                <img src={AGENT_PHOTO} alt="" className="meet__avatar-img" />
              </span>
              {AGENT_NAME} (Presenting)
            </span>
          )}
          <span className="meet__people">
            <MeetIcon name="people" size={16} /> {agentJoined ? 2 : 1}
          </span>
        </div>
      </div>

      {!agentJoined && (
        <div className="meet__banner">{AGENT_NAME} is joining…</div>
      )}

      <div className={`meet__body ${chatOpen ? "meet__body--chat-open" : ""}`}>
        <div
          ref={mainRef}
          className={
            "meet__main " +
            (screenShareActive ? "meet__main--sharing" : agentJoined ? "meet__main--duo" : "meet__main--solo")
          }
        >
          <div className="meet__rail">
            <div className="meet__tile meet__tile--you" data-flip-id="you">
              {/* Live mic state: off, idle, or actively picking up speech —
                  the badge pulses only while genuinely speaking, so it reads
                  as a level meter rather than decoration. */}
              <span
                className={
                  "meet__mic-badge" +
                  (!isMicEnabled ? " meet__mic-badge--off" : isUserSpeaking ? " meet__mic-badge--live" : "")
                }
              >
                <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} size={13} />
              </span>
              {cameraStream ? (
                /* Mirrored, the way every video app shows self-view — an
                   un-mirrored self-view reads as "wrong way round" because
                   it isn't what a mirror does. muted + playsInline so no
                   audio path is created and iOS doesn't force fullscreen. */
                <video
                  ref={selfVideoRef}
                  className="meet__self-video"
                  autoPlay
                  muted
                  playsInline
                />
              ) : (
                <TileAvatar ringRef={youRingRef} letter={initialsFrom(visitorName)} avatarClassName="meet__avatar--tile meet__avatar--you" />
              )}
              <div className="meet__tile-label">You</div>
            </div>
            {/* Always mounted, never conditionally rendered: the tile animates
                open from zero width when she arrives, and a mount would snap
                instead. aria-hidden while she isn't in the room yet. */}
            <div className="meet__tile meet__tile--agent" data-flip-id="agent" aria-hidden={!agentJoined}>
                {/* Two mutually-exclusive states on the agent's tile: an ear
                    while she's listening for you, a mic while she's the one
                    talking. The ear answers the question people actually ask
                    of a voice agent — "is it hearing me right now?" — which a
                    static mic icon never does. Only listening when the mic is
                    live and she isn't mid-sentence. */}
                {isMicEnabled && !isAgentSpeaking ? (
                  <span className="meet__mic-badge meet__mic-badge--listening" title={`${AGENT_NAME} is listening`}>
                    <MeetIcon name="ear" size={13} />
                  </span>
                ) : (
                  <span className={"meet__mic-badge" + (isAgentSpeaking ? " meet__mic-badge--live" : "")}>
                    <MeetIcon name="mic" size={13} />
                  </span>
                )}
                <TileAvatar ringRef={agentRingRef} photo={AGENT_PHOTO} letter={AGENT_INITIAL} avatarClassName="meet__avatar--tile meet__avatar--agent" />
                <div className="meet__tile-label">{AGENT_NAME}</div>
            </div>
          </div>

          {/* Also always mounted — it animates open from zero width when she
              starts presenting. Its children only render once sharing is
              really on, so nothing heavy mounts during the empty phase. */}
          <div className="meet__stage" aria-hidden={!screenShareActive}>
            {screenShareActive && (
              <>
                {/* Mounted for the whole share so the app can cross-fade in
                    underneath it rather than replacing it. */}
                <div
                  className={
                    "meet__share-loader" + (sharePhase === "live" ? " meet__share-loader--done" : "")
                  }
                >
                  <div className="meet__share-loader-badge">
                    <MeetIcon name="screen-share" size={26} />
                    <span className="meet__share-loader-ring" />
                  </div>
                  <div className="meet__share-loader-text">{AGENT_NAME} is presenting her screen</div>
                </div>
                <div
                  className={
                    "meet__stage-inner" + (sharePhase === "live" ? " meet__stage-inner--live" : "")
                  }
                >
                  {children}
                </div>
              </>
            )}
          </div>
        </div>

        {chatOpen && (
          <MeetingChatPanel
            messages={chatMessages}
            onSend={handleSendChat}
            onClose={() => setChatOpen(false)}
          />
        )}
      </div>

      {/* A real blocking modal over the entire call (topbar/controls
          included), not a docked side panel — position:fixed so it's
          anchored to the viewport regardless of where it sits in this
          tree, not constrained by .meet__stage-inner's own transform
          (that only affects position:fixed *descendants* of that element,
          and this isn't one). See ExampleGalleryPanel.tsx's docstring for
          why this is the one surface a visitor can touch directly. */}
      {galleryOpen && <ExampleGalleryPanel onClose={() => setGalleryOpen(false)} />}

      {/* Only appears if the browser blocked the automatic tab (see the
          "booking-portal" registration above). The visitor's click here is a
          real gesture, so this open always succeeds. */}
      {bookingPrompt && (
        <div className="meet__booking-toast">
          <div className="meet__booking-toast-text">Open the booking portal to pick a time?</div>
          <a
            className="meet__booking-toast-go"
            href={BOOKING_LINK_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setBookingPrompt(false)}
          >
            Open booking portal
          </a>
          <button
            className="meet__booking-toast-close"
            onClick={() => setBookingPrompt(false)}
            aria-label="Dismiss"
          >
            <MeetIcon name="dots" size={14} />
          </button>
        </div>
      )}

      {/* Only mic, hand-raise, and hangup are actually wired to real
          behavior right now — camera, screen-share, captions, and the
          overflow menu were removed rather than left as dead, unusable
          buttons (see the "remove useless controls" task). */}
      <div className="meet__controls-hint">
        Tip: press <kbd>Space</kbd> to mute or unmute
      </div>
      <div className="meet__controls">
        <div className="meet__controls-bar">
        <button
          className={`meet__ctrl ${!isMicEnabled ? "meet__ctrl--off" : ""}`}
          onClick={() => enableMic(!isMicEnabled)}
        >
          <MeetIcon name={isMicEnabled ? "mic" : "mic-off"} />
        </button>
        <button
          className={`meet__ctrl ${handRaised ? "meet__ctrl--pressed" : ""}`}
          onClick={handleToggleHandRaise}
          title={
            handRaised
              ? "Lower hand"
              : "Raise hand — the agent will finish its point, then let you ask your question"
          }
        >
          <MeetIcon name="hand" />
        </button>
        <button
          className={`meet__ctrl ${!cameraOn ? "meet__ctrl--off" : ""}`}
          onClick={() => setCameraOn((v) => !v)}
          title={cameraOn ? "Turn off camera" : "Turn on camera"}
        >
          <MeetIcon name={cameraOn ? "camera" : "camera-off"} />
        </button>
        <button
          className={`meet__ctrl ${chatOpen ? "meet__ctrl--active" : ""}`}
          onClick={() => {
            setChatOpen((v) => {
              // Opening is what marks them read — closing must not.
              if (!v) setUnreadChat(0);
              return !v;
            });
          }}
          title={chatOpen ? "Hide in-call messages" : "Show in-call messages"}
        >
          <MeetIcon name="chat" />
          {unreadChat > 0 && !chatOpen && (
            <span className="meet__unread-dot">{unreadChat > 9 ? "9+" : unreadChat}</span>
          )}
        </button>
        {/* Trigger and menu share a positioned wrapper so the popover is
            anchored to the BUTTON. Anchoring it to the strip (as it was)
            put it out at the strip's right edge instead of over the dots. */}
        <div className="meet__more">
          <button
            className={`meet__ctrl meet__ctrl--more ${moreOpen ? "meet__ctrl--active" : ""}`}
            onClick={() => setMoreOpen((v) => !v)}
            title="More options"
            aria-expanded={moreOpen}
          >
            <MeetIcon name="dots-vertical" />
          </button>
        {moreOpen && (
          <div className="meet__more-menu" ref={moreRef} role="menu">
            {MORE_MENU_LINKS.map((l) => (
              <a
                key={l.id}
                className="meet__more-item"
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                role="menuitem"
                onClick={() => setMoreOpen(false)}
              >
                <MeetIcon name={l.icon} size={20} />
                <span>{l.label}</span>
              </a>
            ))}
          </div>
        )}
        </div>

        <button className="meet__ctrl meet__ctrl--hangup" onClick={onLeave}>
          <MeetIcon name="hangup" />
        </button>
        </div>

        {/* Pinned to the row's far left, absolutely positioned so the
            group above stays centred. Carries the same "hall of fame"
            treatment as the badge inside the modal it opens. */}
        <button
          className="meet__showcase-btn"
          onClick={() => setGalleryOpen((v) => !v)}
          title={galleryOpen ? "Hide the content showcase" : "Show the best content showcase"}
        >
          <span className="meet__showcase-btn-inner">
            <span className="meet__showcase-btn-medal">
              <Icon name="trophy" size={14} />
            </span>
            <span className="meet__showcase-btn-text">
              <span className="meet__showcase-btn-kicker">Hall of fame</span>
              <span className="meet__showcase-btn-label">Best Content Showcase</span>
            </span>
          </span>
        </button>

        {/* The always-available route to a human. Opens the same booking
            link the agent sends in chat, in a new tab so the live call is
            never navigated away from. */}
        <a
          className="meet__team-btn"
          href={BOOKING_LINK_URL}
          target="_blank"
          rel="noopener noreferrer"
          title="Book time with a human — opens in a new tab"
        >
          <MeetIcon name="calendar" size={17} />
          <span className="meet__team-btn-label">Talk to the team</span>
        </a>
      </div>
    </div>
  );
}
