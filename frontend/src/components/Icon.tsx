interface IconProps {
  name: string;
  size?: number;
}

const PATHS: Record<string, string> = {
  megaphone: "M3 11v2a1 1 0 0 0 1 1h2l4 4V6L6 10H4a1 1 0 0 0-1 1zm14-6a9 9 0 0 1 0 14",
  stethoscope: "M6 3v5a4 4 0 0 0 8 0V3M10 12v2a5 5 0 0 0 10 0v-1.5M17 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  trophy: "M8 4h8v4a4 4 0 0 1-8 0V4zM5 5h3v2a3 3 0 0 1-3-3zm14 0h-3v2a3 3 0 0 0 3-3zM9 16h6M12 12v4M8 20h8",
  brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1 5.83V15a3 3 0 0 0 3 3h1V4H9zm6 0a3 3 0 0 1 3 3 3 3 0 0 1 1 5.83V15a3 3 0 0 1-3 3h-1V4h0z",
  send: "M22 2 11 13M22 2 15 22l-4-9-9-4 20-7z",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  share: "M18 8a3 3 0 1 0-2.83-4H15a3 3 0 0 0 .1 4.9L9 12.9a3 3 0 1 0 0 2.2l6.1 3.9a3 3 0 1 0 .9-1.7L9.9 13.4a3 3 0 0 0 0-2.8L16 6.7c.5.4 1.2.6 2 .6z",
};

export default function Icon({ name, size = 16 }: IconProps) {
  const d = PATHS[name];
  if (!d) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}
