interface MeetIconProps {
  name: "mic" | "mic-off" | "camera" | "screen-share" | "hand" | "dots" | "hangup" | "captions" | "people" | "info";
  size?: number;
}

export default function MeetIcon({ name, size = 20 }: MeetIconProps) {
  const common = { width: size, height: size, viewBox: "0 0 24 24" };
  switch (name) {
    case "mic":
      return (
        <svg {...common} fill="currentColor">
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
          <line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case "mic-off":
      return (
        <svg {...common} fill="currentColor">
          <rect x="9" y="2" width="6" height="12" rx="3" opacity={0.4} />
          <path d="M5 11a7 7 0 0 0 14 0" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" opacity={0.4} />
          <line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity={0.4} />
          <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case "camera":
      return (
        <svg {...common} fill="currentColor">
          <rect x="2" y="6" width="14" height="12" rx="2.5" />
          <path d="M18 10.5 22 8v8l-4-2.5z" />
        </svg>
      );
    case "screen-share":
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="4" width="20" height="13" rx="2" />
          <path d="M8 21h8M12 17v4M9 11l3-3 3 3M12 8v6" />
        </svg>
      );
    case "hand":
      return (
        <svg {...common} fill="currentColor">
          <path d="M8 11V4a1.5 1.5 0 0 1 3 0v6M11 10V3a1.5 1.5 0 0 1 3 0v7M14 10V4a1.5 1.5 0 0 1 3 0v8M17 12V8a1.5 1.5 0 0 1 3 0v7c0 3.3-2.7 6-6 6h-2c-2.2 0-3.5-.7-4.8-2.3L4 15.6c-.6-.8-.4-1.9.4-2.4.7-.5 1.6-.4 2.2.2L8 15" />
        </svg>
      );
    case "dots":
      return (
        <svg {...common} fill="currentColor">
          <circle cx="5" cy="12" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="19" cy="12" r="2" />
        </svg>
      );
    case "hangup":
      return (
        <svg {...common} fill="currentColor">
          <path d="M12 15.5c-3 0-5.7-.9-8-2.5-.5-.4-.8-1-.7-1.6l.4-2.4c.1-.6.6-1.1 1.2-1.2C7 7.4 9.4 7 12 7s5 .4 7.1.8c.6.1 1.1.6 1.2 1.2l.4 2.4c.1.6-.2 1.2-.7 1.6-2.3 1.6-5 2.5-8 2.5z" />
        </svg>
      );
    case "captions":
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <path d="M7 11a2 2 0 0 0-2 2v0a2 2 0 0 0 2 2h1M15 11a2 2 0 0 0-2 2v0a2 2 0 0 0 2 2h1" />
        </svg>
      );
    case "people":
      return (
        <svg {...common} fill="currentColor">
          <circle cx="9" cy="8" r="3" />
          <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
          <circle cx="18" cy="9" r="2.3" opacity={0.7} />
          <path d="M15.5 20c.2-2.5 1.4-4.6 3.2-5.7 2 .5 3.5 2.6 3.3 5.7" opacity={0.7} />
        </svg>
      );
    case "info":
      return (
        <svg {...common} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" />
          <line x1="12" y1="11" x2="12" y2="16" />
          <circle cx="12" cy="8" r="0.5" fill="currentColor" />
        </svg>
      );
  }
}
