import joinUrl from "../assets/join.mp3";
import messageUrl from "../assets/message.mp3";

// Meeting sound effects. Kept in one place (rather than <audio> elements in
// components) so playback can't be duplicated by a re-render, and so every
// caller gets the same "never throw at the call site" behaviour.
//
// join.mp3 is the real Meet-style join chime, trimmed: the source file had
// 0.64s of leading silence, which made it land noticeably after the thing it
// was announcing. message.mp3 is synthesised (a two-partial bell) rather
// than lifted from a video, so it ships as ours.

const CACHE = new Map<string, HTMLAudioElement>();

function get(url: string, volume: number): HTMLAudioElement {
  let a = CACHE.get(url);
  if (!a) {
    a = new Audio(url);
    a.preload = "auto";
    a.volume = volume;
    CACHE.set(url, a);
  }
  return a;
}

function play(url: string, volume: number) {
  try {
    const a = get(url, volume);
    // Rewind rather than spawning a second element: two joins in quick
    // succession should re-trigger the chime, not overlap into a smear.
    a.currentTime = 0;
    // Autoplay policy rejects this until the page has had a real user
    // gesture. In Meeting Mode there always has been one (the visitor
    // clicked "Join Product Demo"), but a rejected promise must never
    // surface as an unhandled rejection in the console during a live demo.
    void a.play().catch(() => {});
  } catch {
    /* audio is decoration — never let it break the call */
  }
}

/** Someone entered the meeting — the visitor themselves, or the agent. */
export function playJoinSound() {
  play(joinUrl, 0.45);
}

/** A chat message arrived while the panel wasn't open. */
export function playMessageSound() {
  play(messageUrl, 0.4);
}

/** Called once on a real user gesture so the first real chime isn't the
 *  thing that trips the autoplay policy. Silent no-op if it fails. */
export function primeSounds() {
  for (const [url, volume] of [
    [joinUrl, 0.45],
    [messageUrl, 0.4],
  ] as const) {
    try {
      const a = get(url, volume);
      a.load();
    } catch {
      /* ignore */
    }
  }
}
