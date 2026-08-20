import mark from "../assets/swishx-mark.png";
import SwishXWordmark from "./SwishXWordmark";

// The SwishX lockup, reproduced from the brand file's own geometry.
//
// An earlier version placed the mark and the wordmark next to each other by
// hand with a 10px flex gap and independently chosen heights. That is not the
// logo — it is two pieces of the logo arranged to taste, and the taste was
// wrong: the source specifies a gap of ~60 units against a 300-unit mark, so
// 10px beside a 26px mark was almost twice too wide, and the wordmark was set
// a point too short. Small enough to look fine in isolation, wrong enough that
// anyone who knows the mark would see it.
//
// So every dimension here is derived from Swish_X_logo_01.svg rather than
// picked:
//
//   viewBox      0 0 1358 310
//   mark rect    x 1.9   y 4.86   w 285.2   h 300
//   wordmark     x 347   y 50     w 1009    h 210   (measured, getBBox)
//
// which gives a gap of 347 - 287.1 = 59.9 units, and leaves both halves
// centred on the same axis (154.86 vs 155.0). One `height` prop drives all
// three so the proportions can never drift again.
const UNIT_TOTAL = 310;
const UNIT_MARK = 300;
const UNIT_GAP = 59.9;

// Colour is the brand's own #FD4816, from the same file.
//
// The mark ships as a black-on-transparent raster, which is invisible on this
// product's near-black surfaces, so it is painted through its own alpha as a
// CSS mask — the same technique SwishXMark has always used, and the only way
// to place this mark on a dark ground at all. Hue and shape are the brand's;
// nothing else is reinterpreted.
const BRAND = "#fd4816";

export default function SwishXLockup({ height = 26 }: { height?: number }) {
  const markSize = (UNIT_MARK / UNIT_TOTAL) * height;
  const gap = (UNIT_GAP / UNIT_TOTAL) * height;

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
          background: BRAND,
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
      <SwishXWordmark height={height} />
    </span>
  );
}
