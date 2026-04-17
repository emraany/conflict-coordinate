import { useState } from "react";

import { colors, fonts, space } from "../styles/tokens";
import type { CrisisEvent, Source } from "../types";

interface Props {
  events: CrisisEvent[];
  sources: Source[];
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

function sourceRefNumber(sources: Source[], sourceId: number | null): number | null {
  if (sourceId === null) return null;
  const idx = sources.findIndex((s) => s.id === sourceId);
  return idx >= 0 ? idx + 1 : null;
}

export function EventTimeline({ events, sources }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (events.length === 0) {
    return (
      <div className="label" style={{ color: colors.textDim }}>
        (no events recorded)
      </div>
    );
  }

  const sorted = [...events].sort(
    (a, b) =>
      new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime(),
  );

  const toggle = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <ol
      style={{
        margin: 0,
        padding: 0,
        listStyle: "none",
        display: "flex",
        flexDirection: "column",
        gap: space.sm,
      }}
    >
      {sorted.map((ev, i) => {
        const num = String(i + 1).padStart(2, "0");
        const ref = sourceRefNumber(sources, ev.source_id);
        const isOpen = expanded.has(ev.id);
        const description =
          (ev.description && ev.description.trim()) || null;
        const fatalities = ev.fatalities ?? 0;

        const descStyle: React.CSSProperties = {
          margin: `${space.xs}px 0 0 0`,
          fontSize: 13,
          lineHeight: 1.6,
          color: colors.text,
          cursor: description ? "pointer" : "default",
        };
        if (description && !isOpen) {
          descStyle.display = "-webkit-box";
          descStyle.WebkitBoxOrient = "vertical";
          descStyle.WebkitLineClamp = 4;
          descStyle.overflow = "hidden";
        }

        return (
          <li
            key={ev.id}
            style={{
              display: "flex",
              gap: space.md,
              paddingBottom: space.sm,
              borderBottom: `1px dashed ${colors.rule}`,
            }}
          >
            <span
              style={{
                color: colors.textDim,
                fontFamily: fonts.mono,
                fontSize: 11,
                minWidth: 28,
              }}
            >
              [{num}]
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: space.sm,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: colors.textMuted,
                  }}
                >
                  {formatDate(ev.occurred_at)}
                </span>
                {ev.event_type && (
                  <span
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 9,
                      letterSpacing: "0.16em",
                      color: colors.oliveLight,
                      background: colors.bgSunken,
                      border: `1px solid ${colors.oliveDim}`,
                      padding: "1px 6px",
                      textTransform: "uppercase",
                      flexShrink: 0,
                    }}
                  >
                    [ {ev.event_type} ]
                  </span>
                )}
                {fatalities > 0 && (
                  <span
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 11,
                      color: colors.active,
                    }}
                    title="reported fatalities"
                  >
                    † {fatalities}
                  </span>
                )}
              </div>
              {description ? (
                <p
                  className="serif"
                  onClick={() => toggle(ev.id)}
                  style={descStyle}
                >
                  {description}
                </p>
              ) : (
                <p
                  className="label"
                  style={{
                    margin: `${space.xs}px 0 0 0`,
                    fontSize: 11,
                    color: colors.textDim,
                  }}
                >
                  (no description on record)
                </p>
              )}
              <div
                className="label"
                style={{
                  marginTop: 4,
                  fontSize: 10,
                  color: colors.textMuted,
                }}
              >
                {[
                  ev.location_name,
                  ref !== null
                    ? `cited in src §${String(ref).padStart(2, "0")}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
