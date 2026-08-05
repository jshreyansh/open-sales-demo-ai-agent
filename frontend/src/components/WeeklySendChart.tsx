import type { WeeklySendChannel } from "../lib/types";

interface WeeklySendChartProps {
  weeks: string[];
  channels: WeeklySendChannel[];
}

const WIDTH = 460;
const HEIGHT = 220;
const PADDING_LEFT = 36;
const PADDING_RIGHT = 24;
const PADDING_BOTTOM = 20;

export default function WeeklySendChart({ weeks, channels }: WeeklySendChartProps) {
  const max = Math.max(...channels.flatMap((c) => c.values));
  const yMax = Math.ceil(max / 1500) * 1500 || 1500;
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f));
  const chartW = WIDTH - PADDING_LEFT - PADDING_RIGHT;
  const chartH = HEIGHT - PADDING_BOTTOM;
  const step = chartW / (weeks.length - 1);

  function toPoints(values: number[]) {
    return values
      .map((v, i) => `${PADDING_LEFT + i * step},${chartH - (v / yMax) * chartH}`)
      .join(" ");
  }

  return (
    <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
      {gridLines.map((g) => {
        const y = chartH - (g / yMax) * chartH;
        return (
          <g key={g}>
            <line x1={PADDING_LEFT} y1={y} x2={WIDTH - PADDING_RIGHT} y2={y} stroke="rgba(0,0,0,0.06)" />
            <text x={0} y={y + 3} fontSize={9} fill="#9a9a9a">
              {g}
            </text>
          </g>
        );
      })}
      {channels.map((c) => (
        <polyline key={c.channel} points={toPoints(c.values)} fill="none" stroke={c.color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {weeks.map((w, i) => {
        const x = PADDING_LEFT + i * step;
        const anchor = i === weeks.length - 1 ? "end" : i === 0 ? "start" : "middle";
        return (
          <text key={w} x={x} y={HEIGHT - 4} fontSize={9} fill="#9a9a9a" textAnchor={anchor}>
            {w}
          </text>
        );
      })}
    </svg>
  );
}
