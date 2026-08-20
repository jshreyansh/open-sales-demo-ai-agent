import mark from "../../assets/swishx-mark.png";

// The SwishX brand mark, rendered as a CSS alpha MASK rather than as an
// <img>.
//
// The supplied brand file (Swish_X_logo_01.svg) is a horizontal lockup whose
// mark is not vector at all — it's a 3451x3630 base64 PNG embedded in the
// SVG, ~1.1MB of the 1.13MB file. Two problems came with using it directly:
//
//   1. It is pure black on transparent. The old hand-drawn mark was
//      `var(--accent)` orange, and every surface this appears on is dark, so
//      a straight swap rendered a black mark on a near-black header —
//      invisible.
//   2. 1.1MB (831KB gzipped) to draw an 18px icon.
//
// Masking solves both. Because the source is black-on-transparent, its alpha
// channel IS the shape: painting `var(--accent)` through that alpha
// reproduces the original orange mark exactly, and keeps it recolourable if
// a light theme is ever added — the same property the hand-drawn SVG had and
// that a bitmap <img> would have permanently lost.
//
// The PNG is the mark extracted from the lockup and downscaled to 256px
// (41KB), which is ~4x the largest size it's ever drawn at.
//
// Aspect ratio is the source's own 256x269, so the glyph is never squashed;
// `contain` centres it in the square box the call sites lay out for.
export default function SwishXMark({ size = 16 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-block",
        width: size,
        height: size,
        flexShrink: 0,
        background: "var(--accent, #ff4f00)",
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
  );
}
