// Design tokens for the "situation-room briefing" aesthetic.
// Keep in sync with the CSS variables declared in global.css.

export const colors = {
  bg: "#2e3338",
  bgRaised: "#3a4048",
  bgSunken: "#252930",
  text: "#e8dcc4",
  textMuted: "#a8a294",
  textDim: "#7c7a6e",
  rule: "#525862",
  ruleStrong: "#6b727c",
  olive: "#6b7354",
  oliveLight: "#8a9070",
  oliveDim: "#4a523c",
  active: "#a64a3a",
  activeGlow: "rgba(166, 74, 58, 0.35)",
  frozen: "#a8a294",
  resolved: "#5a6358",
  amberReserved: "#c8a96a",
  inkShadow: "rgba(0, 0, 0, 0.55)",
} as const;

export const fonts = {
  mono: `"IBM Plex Mono", "SFMono-Regular", Menlo, Consolas, monospace`,
  stamp: `"Special Elite", "IBM Plex Mono", monospace`,
  serif: `"IBM Plex Serif", Georgia, serif`,
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 40,
  xxl: 64,
} as const;

export const radii = {
  none: 0,
  sm: 2,
  md: 4,
} as const;

export const motion = {
  fast: "120ms",
  base: "180ms",
  easing: "cubic-bezier(0.4, 0.0, 0.2, 1)",
} as const;

export const statusColor = (status: string): string => {
  switch (status) {
    case "active":
      return colors.active;
    case "frozen":
      return colors.frozen;
    case "resolved":
      return colors.resolved;
    default:
      return colors.textMuted;
  }
};
