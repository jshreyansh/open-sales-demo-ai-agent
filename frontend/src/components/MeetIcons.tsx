import {
  mdiMicrophone,
  mdiMicrophoneOff,
  mdiVideo,
  mdiVideoOff,
  mdiMonitorShare,
  mdiClosedCaption,
  mdiHandBackRight,
  mdiDotsHorizontal,
  mdiPhoneHangup,
  mdiAccountMultiple,
  mdiAccount,
  mdiInformationOutline,
  mdiMapMarkerOutline,
  mdiMessageTextOutline,
  mdiSend,
} from "@mdi/js";

interface MeetIconProps {
  name:
    | "mic"
    | "mic-off"
    | "camera"
    | "camera-off"
    | "screen-share"
    | "hand"
    | "dots"
    | "hangup"
    | "captions"
    | "people"
    | "account"
    | "info"
    | "location"
    | "chat"
    | "send";
  size?: number;
}

// Real Material Design Icons (via @mdi/js) instead of hand-rolled SVGs — the
// old paths rendered inconsistent/broken shapes at small sizes (e.g. the
// hangup icon looked like a blank pill).
const PATHS: Record<MeetIconProps["name"], string> = {
  mic: mdiMicrophone,
  "mic-off": mdiMicrophoneOff,
  camera: mdiVideo,
  "camera-off": mdiVideoOff,
  "screen-share": mdiMonitorShare,
  captions: mdiClosedCaption,
  hand: mdiHandBackRight,
  dots: mdiDotsHorizontal,
  hangup: mdiPhoneHangup,
  people: mdiAccountMultiple,
  account: mdiAccount,
  info: mdiInformationOutline,
  location: mdiMapMarkerOutline,
  chat: mdiMessageTextOutline,
  send: mdiSend,
};

export default function MeetIcon({ name, size = 20 }: MeetIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      <path d={PATHS[name]} fill="currentColor" />
    </svg>
  );
}
