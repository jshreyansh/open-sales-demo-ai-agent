import {
  mdiMicrophone,
  mdiPause,
  mdiViewGridOutline,
  mdiBookOpenPageVariantOutline,
  mdiPlay,
  mdiMicrophoneOff,
  mdiVideo,
  mdiVideoOff,
  mdiMonitorShare,
  mdiClosedCaption,
  mdiHandBackRight,
  mdiDotsHorizontal,
  mdiDotsVertical,
  mdiPhoneHangup,
  mdiAccountMultiple,
  mdiAccount,
  mdiInformationOutline,
  mdiMapMarkerOutline,
  mdiMessageTextOutline,
  mdiSend,
  mdiStarOutline,
  mdiEarHearing,
  mdiClose,
  mdiLinkedin,
  mdiFileDocumentOutline,
  mdiCalendarMonthOutline,
} from "@mdi/js";

interface MeetIconProps {
  name:
    | "mic"
    | "pause"
    | "grid"
    | "book"
    | "play"
    | "mic-off"
    | "camera"
    | "camera-off"
    | "screen-share"
    | "hand"
    | "dots"
    | "dots-vertical"
    | "hangup"
    | "captions"
    | "people"
    | "account"
    | "info"
    | "location"
    | "chat"
    | "send"
    | "highlights"
    | "ear"
    | "close"
    | "linkedin"
    | "docs"
    | "calendar"
    | "x";
  size?: number;
}

// Real Material Design Icons (via @mdi/js) instead of hand-rolled SVGs — the
// old paths rendered inconsistent/broken shapes at small sizes (e.g. the
// hangup icon looked like a blank pill).
const PATHS: Record<MeetIconProps["name"], string> = {
  mic: mdiMicrophone,
  // Play/pause for the whole agent. The two shapes every media player
  // already uses — this control does exactly what people expect, so it
  // should not invent a symbol for it.
  pause: mdiPause,
  // Nav glyphs for the landing header. All three items carry one now — two
  // bare labels beside one iconned pill read as an accident rather than a
  // hierarchy.
  grid: mdiViewGridOutline,
  book: mdiBookOpenPageVariantOutline,
  play: mdiPlay,
  "mic-off": mdiMicrophoneOff,
  camera: mdiVideo,
  "camera-off": mdiVideoOff,
  "screen-share": mdiMonitorShare,
  captions: mdiClosedCaption,
  hand: mdiHandBackRight,
  dots: mdiDotsHorizontal,
  "dots-vertical": mdiDotsVertical,
  hangup: mdiPhoneHangup,
  people: mdiAccountMultiple,
  account: mdiAccount,
  info: mdiInformationOutline,
  location: mdiMapMarkerOutline,
  chat: mdiMessageTextOutline,
  send: mdiSend,
  highlights: mdiStarOutline,
  // The agent's "I'm listening" indicator (see .meet__ear-badge) — an ear
  // with sound waves, the same glyph other voice products use for this.
  ear: mdiEarHearing,
  close: mdiClose,
  linkedin: mdiLinkedin,
  docs: mdiFileDocumentOutline,
  calendar: mdiCalendarMonthOutline,
  // X's current mark. Not in @mdi/js (which still ships the old Twitter
  // bird), so it's the official glyph inlined — same 24x24 box and fill
  // convention as every other path here, so MeetIcon renders it unchanged.
  x: "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z",
};

export default function MeetIcon({ name, size = 20 }: MeetIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <path d={PATHS[name]} fill="currentColor" />
    </svg>
  );
}
