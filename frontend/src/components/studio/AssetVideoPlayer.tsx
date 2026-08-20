import { forwardRef, useImperativeHandle, useRef } from "react";

export interface AssetVideoPlayerHandle {
  play: () => void;
}

interface AssetVideoPlayerProps {
  src: string;
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
const AssetVideoPlayer = forwardRef<AssetVideoPlayerHandle, AssetVideoPlayerProps>(({ src }, ref) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useImperativeHandle(ref, () => ({
    play: () => {
      void videoRef.current?.play();
    },
  }));

  return (
    <div className="scene-inspector__player asset-video-player">
      <video ref={videoRef} src={src} className="asset-video-player__video" controls playsInline />
    </div>
  );
});

AssetVideoPlayer.displayName = "AssetVideoPlayer";
export default AssetVideoPlayer;
