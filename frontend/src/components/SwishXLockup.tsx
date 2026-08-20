import mark from "../assets/swishx-mark.png";
import wordmark from "../assets/swishx-wordmark-white.png";

// The SwishX lockup for dark surfaces.
//
// Two earlier attempts got this wrong in the same way: they treated the logo
// as parts to be arranged and coloured. It isn't. On a dark ground the brand
// is a WHITE mark with a white "swish" and an orange "X" — the supplied
// White_SX_logo.png is exactly that, so the wordmark is now that file, used
// as-is with no recolouring at all.
//
// (The horizontal SVG lockup is the LIGHT-background artwork: black mark,
// #FD4816 wordmark. Painting the whole thing orange to make it visible on
// black was my invention, and it was wrong — orange "swish" instead of
// white.)
//
// The mark still comes through a CSS alpha mask rather than as its own image,
// because the only copy of it that exists standalone is black-on-transparent.
// Masking it to #FFFFFF reproduces the white mark from the social asset
// exactly — same shape, same colour, no reinterpretation.
//
// Proportions are the brand file's, not eyeballed:
//
//   viewBox    0 0 1358 310
//   mark rect  x 1.9  y 4.86  w 285.2  h 300
//   wordmark   x 347  y 50    w 1009   h 210   (measured, getBBox)
//
// giving a gap of 347 - 287.1 = 59.9 units against a 300-unit mark, with both
// halves centred on the same axis. One `height` prop drives all three so the
// spacing can't drift again — an earlier version used a hand-picked 10px gap,
// nearly double what the artwork specifies.
const UNIT_TOTAL = 310;
const UNIT_MARK = 300;
const UNIT_GAP = 59.9;
const UNIT_WORDMARK = 210;

export default function SwishXLockup({ height = 28 }: { height?: number }) {
  const markSize = (UNIT_MARK / UNIT_TOTAL) * height;
  const gap = (UNIT_GAP / UNIT_TOTAL) * height;
  const typeHeight = (UNIT_WORDMARK / UNIT_TOTAL) * height;

  return (
    <span
      className="swishx-lockup"
      role="img"
      aria-label="SwishX"
      style={{ display: "inline-flex", alignItems: "center", gap: `${gap}px` }}
    >
      <span
        aria-hidden="true"
        style={{
          width: markSize,
          height: markSize,
          flexShrink: 0,
          background: "#ffffff",
          WebkitMaskImage: `url(${mark})`,
          maskImage: `url(${mark})`,
          WebkitMaskSize: "contain",
          maskSize: "contain",
          WebkitMaskRepeat: "no-repeat",
          maskRepeat: "no-repeat",
          WebkitMaskPosition: "center",
          maskPosition: "center",
        }}
      />
      <img src={wordmark} alt="" aria-hidden="true" style={{ height: typeHeight, width: "auto", display: "block" }} />
    </span>
  );
}
