// Design tokens for the "situation-room briefing" aesthetic.
// Keep in sync with the CSS variables declared in global.css.

export const colors = {
  bg: "#0b0d10",
  bgRaised: "#11141a",
  text: "#e8dcc4",
  textMuted: "#8a8578",
  textDim: "#5b5a53",
  rule: "#2a2d33",
  ruleStrong: "#3d4048",
  active: "#b3332a",
  activeGlow: "rgba(179, 51, 42, 0.35)",
  amber: "#c8a96a",
  olive: "#5a6358",
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
      return colors.amber;
    case "resolved":
      return colors.olive;
    default:
      return colors.textMuted;
  }
};
