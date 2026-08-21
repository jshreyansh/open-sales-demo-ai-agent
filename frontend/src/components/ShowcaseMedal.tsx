import emblem from "../assets/swishx-emblem.png";
import Icon from "./Icon";

// The medal inside the "Best Content Showcase" badge.
//
// It used to be a static trophy. It now alternates between that trophy and
// the SwishX emblem, because the badge is making a claim about OUR work —
// the mark belongs in it, and a thing that quietly changes gets looked at
// twice where a static icon gets looked at once.
//
// Both glyphs are black on the same orange tile, and both are round-ish
// shapes of the same visual weight, so the swap reads as one object turning
// rather than two icons swapping places. That is the whole reason this is a
// 3D flip on the Y axis and not a crossfade: a flip says "same object, other
// face", which is true here.
//
// Lives in one component used by both the meeting's control strip and the
// landing page, so the two can't drift.
export default function ShowcaseMedal({ size = 14 }: { size?: number }) {
  return (
    <span className="showcase-medal" aria-hidden="true">
      <span className="showcase-medal__face showcase-medal__face--trophy">
        <Icon name="trophy" size={size} />
      </span>
      <span className="showcase-medal__face showcase-medal__face--emblem">
        <img src={emblem} alt="" width={size + 2} height={size + 2} />
      </span>
    </span>
  );
}
