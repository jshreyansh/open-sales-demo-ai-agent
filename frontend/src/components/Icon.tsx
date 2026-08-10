interface IconProps {
  name: string;
  size?: number;
  className?: string;
}

const PATHS: Record<string, string> = {
  megaphone: "M3 11v2a1 1 0 0 0 1 1h2l4 4V6L6 10H4a1 1 0 0 0-1 1zm14-6a9 9 0 0 1 0 14",
  stethoscope: "M6 3v5a4 4 0 0 0 8 0V3M10 12v2a5 5 0 0 0 10 0v-1.5M17 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  trophy: "M8 4h8v4a4 4 0 0 1-8 0V4zM5 5h3v2a3 3 0 0 1-3-3zm14 0h-3v2a3 3 0 0 0 3-3zM9 16h6M12 12v4M8 20h8",
  brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1 5.83V15a3 3 0 0 0 3 3h1V4H9zm6 0a3 3 0 0 1 3 3 3 3 0 0 1 1 5.83V15a3 3 0 0 1-3 3h-1V4h0z",
  send: "M22 2 11 13M22 2 15 22l-4-9-9-4 20-7z",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  share: "M18 8a3 3 0 1 0-2.83-4H15a3 3 0 0 0 .1 4.9L9 12.9a3 3 0 1 0 0 2.2l6.1 3.9a3 3 0 1 0 .9-1.7L9.9 13.4a3 3 0 0 0 0-2.8L16 6.7c.5.4 1.2.6 2 .6z",
  // ---- sidebar nav icons ----
  dashboard: "M3 3h8v8H3zM13 3h8v8h-8zM3 13h8v8H3zM13 13h8v8h-8z",
  "bar-chart": "M3 3v18h18M7 16v-4M12 16V8M17 16v-7",
  sparkles: "M12 2l1.5 5L19 9l-5.5 2L12 16l-1.5-5L5 9l5.5-2zM19 15l.6 2 2 .6-2 .6-.6 2-.6-2-2-.6 2-.6z",
  play: "M6 4l14 8-14 8V4z",
  layers: "M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  mail: "M3 5h18v14H3zM3 5l9 7 9-7",
  image: "M3 4h18v16H3zM8 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM21 17l-6-6-4 4-3-3-5 5",
  "file-text": "M6 2h9l5 5v15H6zM15 2v5h5M9 13h6M9 17h6M9 9h2",
  "book-open": "M4 5c2-1 5-1 7 0v14c-2-1-5-1-7 0zM20 5c-2-1-5-1-7 0v14c2-1 5-1 7 0z",
  palette: "M12 21a9 9 0 1 1 0-18c5 0 8 3 8 7 0 2-1 3-3 3h-2a2 2 0 0 0 0 4 2 2 0 0 1-3 4zM7 12a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM9.5 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM14.5 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  folder: "M3 6h6l2 2h10v11H3z",
  quote: "M7 7c-2 0-3 1.5-3 3.5S5 14 7 14c0-3 1-4 3-4V7H7zM15 7c-2 0-3 1.5-3 3.5s1 3.5 3 3.5c0-3 1-4 3-4V7h-3z",
  "layout-grid": "M3 4h18v16H3zM3 9h18M9 9v11",
  shield: "M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21c0-4 3-7 7-7s7 3 7 7M17 11a3 3 0 1 0 0-6M23 21c0-3-2-5.5-4-6.5",
  "refresh-cw": "M21 12a9 9 0 0 1-9 9 9 9 0 0 1-8-5M3 12a9 9 0 0 1 9-9 9 9 0 0 1 8 5M21 3v5h-5M3 21v-5h5",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  "sidebar-collapse": "M3 4h18v16H3zM9 4v16M13 10l-2 2 2 2",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35",
  bell: "M6 10a6 6 0 1 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6zM9 20a3 3 0 0 0 6 0",
  moon: "M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5 7 7 0 0 0 20.5 14.5z",
  "chevron-down": "M6 9l6 6 6-6",
  x: "M18 6 6 18M6 6l12 12",
  "check-circle": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM8 12l3 3 5-6",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 7v5l3.5 2",
  minus: "M5 12h14",
  mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8",
  ban: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM4.9 4.9l14.2 14.2",
  expand: "M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3",
  collapse: "M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3",
  menu: "M3 6h18M3 12h18M3 18h18",
};

export default function Icon({ name, size = 16, className }: IconProps) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d={d} />
    </svg>
  );
}
