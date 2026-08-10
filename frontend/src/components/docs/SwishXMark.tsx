// A small, crisp sparkle mark in the app's own accent color — used instead
// of swishx-docs' actual brand SVG, which turned out to be a ~1MB
// raster-image-in-SVG export (fine for a marketing site, not for an icon
// rendered at 14-18px in a header that should load fast).
export default function SwishXMark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 2c0 4-1 6.5-3 8.5S2.5 12 2 12c4 0 6.5 1 8.5 3S12 21.5 12 22c0-4 1-6.5 3-8.5S21.5 12 22 12c-4 0-6.5-1-8.5-3S12 2.5 12 2z"
        fill="var(--accent, #ff4f00)"
      />
    </svg>
  );
}
