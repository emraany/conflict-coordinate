import type { ReactNode } from "react";
import { colors, fonts, space } from "../styles/tokens";

interface Props {
  children: ReactNode;
  rightMeta?: ReactNode;
}

export function Brief({ children, rightMeta }: Props) {
  const now = new Date();
  const dateStamp = now
    .toISOString()
    .replace("T", " ")
    .slice(0, 16)
    .toUpperCase() + " UTC";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        width: "100vw",
        background: colors.bg,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: `${space.sm}px ${space.lg}px`,
          borderBottom: `1px solid ${colors.rule}`,
          background: colors.bgRaised,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: space.md }}>
          <span
            className="stamp"
            style={{ fontSize: 16, color: colors.text, letterSpacing: "0.22em" }}
          >
            THE CONFLICT COORDINATE
          </span>
          <span
            className="label"
            style={{ color: colors.textDim, fontSize: 10 }}
          >
            // OPERATIONAL BRIEF
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: space.lg,
            fontFamily: fonts.mono,
            fontSize: 11,
            color: colors.textMuted,
          }}
        >
          {rightMeta}
          <span>REF // {dateStamp}</span>
        </div>
      </header>

      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        {children}
      </div>

      <footer
        className="classified-stripe"
        style={{
          fontSize: 10,
          letterSpacing: "0.2em",
          color: colors.textMuted,
          textAlign: "center",
          flexShrink: 0,
        }}
      >
        <span className="stamp" style={{ color: colors.active }}>
          DEVELOPMENT FIXTURE
        </span>{" "}
        — ALL CLAIMS ATTRIBUTED TO LINKED SOURCES. NO EDITORIAL INTERPRETATION.
      </footer>
    </div>
  );
}
