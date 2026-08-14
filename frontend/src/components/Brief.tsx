import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { HealthStatus } from "../types";
import { navigate } from "../utils/navigate";
import { colors, fonts, space } from "../styles/tokens";

type Section = "globe" | "index" | "activity" | "about";

interface NavItem {
  num: string;
  label: string;
  section: Section;
  path: string;
}

const NAV: NavItem[] = [
  { num: "01", label: "GLOBE", section: "globe", path: "/" },
  { num: "02", label: "INDEX", section: "index", path: "/conflicts" },
  { num: "03", label: "ACTIVITY", section: "activity", path: "/activity" },
  { num: "04", label: "ABOUT", section: "about", path: "/about" },
];

interface Props {
  children: ReactNode;
  rightMeta?: ReactNode;
  section?: Section;
}

/** How long since the pipeline last succeeded — the only honest freshness claim. */
function ingestStamp(health: HealthStatus | null, unreachable: boolean): string {
  if (unreachable) return "API UNREACHABLE";
  if (!health) return "…";
  const days = health.days_since_successful_ingest;
  if (days === null) return "NO RUN ON RECORD";
  if (days === 0) return "TODAY";
  if (days === 1) return "1 DAY AGO";
  return `${days} DAYS AGO`;
}

export function Brief({ children, rightMeta, section }: Props) {
  // Data currency, not wall-clock time. The footer used to stamp the
  // browser's own clock, which tracked nothing: a pipeline stalled for a
  // month still rendered a stamp reading "now".
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getHealth()
      .then((h) => !cancelled && setHealth(h))
      .catch(() => !cancelled && setUnreachable(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const stale = health?.status === "stale" || health?.status === "degraded";

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

        {/* Section nav — right side of header */}
        <nav style={{ display: "flex", gap: space.lg }}>
          {NAV.map((item) => {
            const active = item.section === section;
            return (
              <button
                key={item.section}
                onClick={() => navigate(item.path)}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  letterSpacing: "0.18em",
                  color: active ? colors.oliveLight : colors.textMuted,
                  opacity: active ? 1 : 0.65,
                  transition: "color 150ms, opacity 150ms",
                }}
              >
                {active ? "> " : ""}[{item.num}] {item.label}
              </button>
            );
          })}
        </nav>
      </header>

      <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
        {children}
      </div>

      <footer
        className="classified-stripe"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          padding: `0 ${space.lg}px`,
        }}
      >
        {/* rightMeta + timestamp — footer left */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: space.lg,
            fontFamily: fonts.mono,
            fontSize: 10,
            color: colors.textMuted,
          }}
        >
          {rightMeta}
          {health && (
            <span>DATA // WEEK ENDING {health.latest_aggregate_week ?? "—"}</span>
          )}
          <span>INGEST // {ingestStamp(health, unreachable)}</span>
        </div>

        <span
          style={{
            fontSize: 10,
            letterSpacing: "0.2em",
            color: colors.textMuted,
          }}
        >
          {stale && (
            <>
              <span className="stamp" style={{ color: colors.active }}>
                DATA MAY BE STALE
              </span>{" "}
              —{" "}
            </>
          )}
          ACLED · UCDP · GDELT · RELIEFWEB — ALL CLAIMS ATTRIBUTED TO LINKED
          SOURCES. NO EDITORIAL INTERPRETATION.
        </span>
      </footer>
    </div>
  );
}
