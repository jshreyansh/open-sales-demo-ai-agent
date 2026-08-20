import { useEffect, useRef, useState } from "react";

// Real self-view camera for the meeting's "You" tile.
//
// Nothing here is sent anywhere: the MediaStream is attached straight to a
// local <video> element and never added to the WebRTC peer connection, never
// recorded, never uploaded. It exists purely so the visitor sees themselves
// the way they would in any real call — which is also why the browser's own
// permission prompt is the only gate, and why the stream is torn down the
// moment the camera is switched off rather than left running idle.

export type CameraStatus = "off" | "starting" | "on" | "denied" | "unavailable";

export function useLocalCamera(enabled: boolean) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>("off");
  // Guards against an out-of-order resolve: flipping the camera off (or on
  // again) while getUserMedia is still pending would otherwise land a stale
  // stream in state with nothing left to stop it.
  const requestId = useRef(0);

  useEffect(() => {
    const id = ++requestId.current;

    if (!enabled) {
      setStatus("off");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("unavailable");
      return;
    }

    let cancelled = false;
    let local: MediaStream | null = null;

    setStatus("starting");
    navigator.mediaDevices
      // Video only. Asking for audio here would pop a second permission
      // prompt and fight the voice pipeline, which already owns the mic.
      .getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false })
      .then((s) => {
        if (cancelled || id !== requestId.current) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        local = s;
        setStream(s);
        setStatus("on");
      })
      .catch((err: unknown) => {
        if (cancelled || id !== requestId.current) return;
        const name = (err as { name?: string })?.name;
        // NotAllowedError covers both an explicit "Block" and a dismissed
        // prompt; everything else (no camera attached, device in use by
        // another app, insecure origin) reads as unavailable.
        setStatus(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "unavailable");
      });

    return () => {
      cancelled = true;
      if (local) local.getTracks().forEach((t) => t.stop());
      setStream((prev) => {
        if (prev && prev !== local) prev.getTracks().forEach((t) => t.stop());
        return null;
      });
    };
  }, [enabled]);

  return { stream, status };
}
