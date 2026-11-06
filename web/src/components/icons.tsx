// One icon set: 16 px grid, 1.5 px stroke, round caps. Decorative; the text next to each icon carries the meaning.

type P = { size?: number };

function Svg({ size = 16, children }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export const IconQuestion = (p: P) => (
  <Svg {...p}><circle cx="8" cy="8" r="6.25" /><path d="M6.3 6.2a1.8 1.8 0 1 1 2.5 1.7c-.5.2-.8.6-.8 1.1v.3" /><path d="M8 11.4h.01" strokeWidth="2" /></Svg>
);
export const IconBlock = (p: P) => (
  <Svg {...p}><circle cx="8" cy="8" r="6.25" /><path d="M3.6 12.4l8.8-8.8" /></Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}><path d="M8 1.9l6.4 11.2H1.6z" /><path d="M8 6.4v3" /><path d="M8 11.3h.01" strokeWidth="2" /></Svg>
);
export const IconClock = (p: P) => (
  <Svg {...p}><circle cx="8" cy="8" r="6.25" /><path d="M8 4.6V8l2.2 1.4" /></Svg>
);
export const IconSearchOff = (p: P) => (
  <Svg {...p}><circle cx="7" cy="7" r="4.5" /><path d="M10.4 10.4l3.6 3.6" /><path d="M5.4 7h3.2" /></Svg>
);
export const IconCalendar = (p: P) => (
  <Svg {...p}><rect x="2" y="3" width="12" height="11" rx="2" /><path d="M2 6.5h12M5.5 1.8v2.4M10.5 1.8v2.4" /></Svg>
);
export const IconCheck = (p: P) => (
  <Svg {...p}><path d="M3.5 8.3l2.9 2.9 6.1-6.4" /></Svg>
);
export const IconCopy = (p: P) => (
  <Svg {...p}><rect x="5.5" y="5.5" width="8" height="8" rx="1.5" /><path d="M10.5 3.5v-.5A1.5 1.5 0 0 0 9 1.5H3A1.5 1.5 0 0 0 1.5 3v6A1.5 1.5 0 0 0 3 10.5h.5" /></Svg>
);
export const IconChevron = (p: P) => (
  <Svg {...p}><path d="M6 3.5L10.5 8 6 12.5" /></Svg>
);
export const IconArrow = (p: P) => (
  <Svg {...p}><path d="M2.5 8h10.5M9 4l4 4-4 4" /></Svg>
);
export const IconRetry = (p: P) => (
  <Svg {...p}><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9" /><path d="M13.6 2.2v2.9h-2.9" /></Svg>
);
export const IconSun = (p: P) => (
  <Svg {...p}><circle cx="8" cy="8" r="2.9" /><path d="M8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" /></Svg>
);
export const IconMoon = (p: P) => (
  <Svg {...p}><path d="M13.4 9.6A5.6 5.6 0 0 1 6.4 2.6a5.6 5.6 0 1 0 7 7z" /></Svg>
);
export const IconMonitor = (p: P) => (
  <Svg {...p}><rect x="1.8" y="2.5" width="12.4" height="8.5" rx="1.5" /><path d="M5.5 14h5M8 11v3" /></Svg>
);
