interface SparklineProps {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  /** Stretch to fill the parent instead of holding the 90x24 aspect.
      Needed for the dashboard tiles, where the line runs the full width of
      the card's foot: with the default preserveAspectRatio the svg letterboxes
      itself to a ~150px island in the middle of a 480px band. */
  fluid?: boolean;
}

export default function Sparkline({ values, color, width = 90, height = 24, fluid = false }: SparklineProps) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const coords = values.map((v, i) => [i * step, height - ((v - min) / range) * height] as const);
  const points = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const areaPoints = `0,${height} ${points} ${width},${height}`;
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    <svg
      width={fluid ? undefined : width}
      height={fluid ? undefined : height}
      viewBox={`0 0 ${width} ${height}`}
      /* Non-uniform stretch would smear the stroke thin horizontally, so the
         stroke is taken out of the transform. */
      preserveAspectRatio={fluid ? "none" : undefined}
    >
      <polygon points={areaPoints} fill={color} opacity={0.12} />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect={fluid ? "non-scaling-stroke" : undefined}
      />
      {/* Where the trend ends is the only point on the line anyone actually
          looks for, so it gets a dot. */}
      {fluid && <circle cx={lastX} cy={lastY} r={2} fill={color} vectorEffect="non-scaling-stroke" />}
    </svg>
  );
}
