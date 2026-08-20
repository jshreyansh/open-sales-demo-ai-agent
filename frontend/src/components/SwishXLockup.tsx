import wordmark from "../assets/swishx-wordmark-white.png";

// The SwishX logo for dark surfaces: the supplied artwork, drawn as-is.
//
// There is no mark here on purpose. Three earlier versions paired the
// wordmark with the brand mark, and every one of them got the mark wrong,
// because the only standalone copy of it in this repo is black-on-transparent
// artwork meant for light backgrounds — so putting it on a dark page always
// meant recolouring it, and recolouring someone's mark is exactly the thing
// you don't get to do. Orange "swish" was the worst of those attempts.
//
// White_SX_logo.png is the finished dark-surface wordmark. No mask, no tint,
// no reconstruction from parts: one <img>, its own pixels, its own colours.
// If the mark is ever wanted back, it needs to arrive as its own white-on-
// transparent asset rather than being derived from the light-background one.
export default function SwishXLockup({ height = 22 }: { height?: number }) {
  return (
    <img
      src={wordmark}
      alt="SwishX"
      className="swishx-lockup"
      style={{ height, width: "auto", display: "block" }}
    />
  );
}
