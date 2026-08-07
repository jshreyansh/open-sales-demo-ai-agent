import { useEffect, useRef } from "react";

// Always-present base look: a soft drop shadow ("elevated" off the tile
// background) plus a faint permanent light-blue tint right on the photo's
// edge — Meet's speaking indicator isn't a ring that appears from nothing,
// it's a thin edge stroke that's always faintly there and a soft glow that
// intensifies with volume, not a separate hard-edged ring floating around
// the photo with a gap.
const ELEVATION = "0 6px 18px rgba(0, 0, 0, 0.35)";
const TINT_RGB = "138, 180, 248"; // Meet's speaking-indicator blue

/**
 * Shared by both ring sources (this file's live MediaStreamTrack analyser,
 * and useReportedAudioLevelRing's server-message-driven one) so the two
 * tiles look identically responsive at the same level value, whichever
 * source it came from.
 */
export function applyLevelToRing(el: HTMLElement, level: number) {
  const strokeOpacity = 0.45 + level * 0.55;
  const glowBlur = 14 + level * 46;
  const glowSpread = 6 + level * 6;
  const glowOpacity = 0.3 + level * 0.6;
  el.style.boxShadow = [
    ELEVATION,
    `0 0 0 3px rgba(${TINT_RGB}, ${strokeOpacity})`,
    `0 0 ${glowBlur}px ${glowSpread}px rgba(${TINT_RGB}, ${glowOpacity})`,
  ].join(", ");
}

/**
 * Drives an avatar's box-shadow from a MediaStreamTrack's *real* amplitude —
 * not a canned pulse animation and not the pipecat client's own
 * localAudioLevel/remoteAudioLevel RTVI events (those are only wired up for
 * the Daily.co transport bundled in @pipecat-ai/small-webrtc-transport; our
 * SmallWebRTCTransport doesn't emit them). The track itself is real, though
 * (usePipecatClientMediaTrack), so we build a small Web Audio API analyser
 * on top of it directly.
 *
 * Deliberately box-shadow on the avatar itself, not a separate larger ring
 * element floating around it with a gap — a tight zero-blur shadow sits
 * right on the photo's edge (the "stroke"), and a second, blurred shadow
 * layered behind it is the soft glow, with no hard edge of its own.
 *
 * Updates land straight on the DOM node via the ref, not through React
 * state — this runs on every animation frame, and re-rendering a component
 * at 60fps for a CSS box-shadow is unnecessary work react would otherwise do
 * for us for free if we just set style properties directly.
 *
 * The analyser is intentionally NOT connected to audioContext.destination —
 * this taps the track for analysis only. For the bot's remote audio track,
 * actual playback already happens through <PipecatClientAudio />; wiring
 * this analyser to destination too would double up that output.
 */
export function useAudioLevelRing(track: MediaStreamTrack | null | undefined) {
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!track) return;

    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(new MediaStream([track]));
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.6;
    source.connect(analyser);

    const data = new Uint8Array(analyser.frequencyBinCount);
    let rafId: number;

    function tick() {
      analyser.getByteTimeDomainData(data);
      // RMS of the waveform — each byte is centered at 128 for unsigned 8-bit PCM.
      let sumSquares = 0;
      for (let i = 0; i < data.length; i++) {
        const normalized = (data[i] - 128) / 128;
        sumSquares += normalized * normalized;
      }
      const rms = Math.sqrt(sumSquares / data.length);
      // Typical speech RMS on this scale sits well under 1 — boost sensitivity
      // so normal talking volume actually moves the ring, not just shouting.
      const level = Math.min(1, rms * 4);

      const el = ringRef.current;
      if (el) applyLevelToRing(el, level);
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      source.disconnect();
      analyser.disconnect();
      void audioContext.close();
    };
  }, [track]);

  return ringRef;
}
