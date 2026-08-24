import { forwardRef, useImperativeHandle, useRef } from "react";
import Icon from "../Icon";

export interface AssetVideoPlayerHandle {
  play: () => void;
}

interface AssetVideoPlayerProps {
  src: string;
  // The wizard result screens (MagicReel/MagicAvatar's own Generate step)
  // show a real render here, but it isn't meant to be something a visitor
  // clicks through mid-demo — the one place a video is actually meant to be
  // watched is the Best Content Showcase (see ExampleGalleryPanel, the only
  // caller that leaves this false). Locked drops the native <video controls>
  // so there's nothing for a visitor to click, and shows a lock badge so
  // that reads as deliberate rather than broken. play() still works via ref
  // either way — the agent narrating "and here's the rendered video" is a
  // scripted beat, not a visitor clicking play, and locking that out too
  // would leave the wizard's own result screen looking finished but mute.
  locked?: boolean;
}

// A real <video controls> element -- the browser's own native player (play/
// pause, volume, scrub, fullscreen), not a hand-rolled play button + progress
// bar. Confirmed live: the custom UI read as unresponsive/"hanging" next to
// controls everyone already knows how to use, and there's no real reason to
// rebuild what every browser already ships. `play()` stays exposed via ref
// for the wizard result screens, where the agent (not the visitor) triggers
// playback on "play that video" -- native controls don't get in the way of
// that, they just also let a human press play directly wherever that's
// allowed (see ExampleGalleryPanel, the one meeting surface a visitor can
// actually touch).
const AssetVideoPlayer = forwardRef<AssetVideoPlayerHandle, AssetVideoPlayerProps>(({ src, locked = false }, ref) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useImperativeHandle(ref, () => ({
    play: () => {
      void videoRef.current?.play();
    },
  }));

  return (
    <div className={`scene-inspector__player asset-video-player${locked ? " asset-video-player--locked" : ""}`}>
      <video
        ref={videoRef}
        src={src}
        className="asset-video-player__video"
        controls={!locked}
        playsInline
      />
      {locked && (
        <div className="asset-video-player__lock" aria-hidden="true">
          <Icon name="lock" size={22} />
        </div>
      )}
    </div>
  );
});

AssetVideoPlayer.displayName = "AssetVideoPlayer";
export default AssetVideoPlayer;
