import { useState } from "react";

import { colors, fonts, space } from "../styles/tokens";
import type { CrisisEvent } from "../types";

interface Props {
  events: CrisisEvent[];
  sourceIndex: Map<number, number>;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

export function EventTimeline({ events, sourceIndex }: Props) {
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
        gap: 0,
      }}
    >
      {sorted.map((ev, i) => {
        const isLast = i === sorted.length - 1;
        const num = String(i + 1).padStart(2, "0");
        const ref = ev.source_id != null ? sourceIndex.get(ev.source_id) ?? null : null;
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
              gap: 0,
            }}
          >
            {/* Vertical line + dot column */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                width: 28,
                flexShrink: 0,
                marginRight: space.md,
              }}
            >
              {/* Dot */}
              <div
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: colors.oliveDim,
                  border: `1px solid ${colors.oliveLight}`,
                  flexShrink: 0,
                  marginTop: 3,
                  zIndex: 1,
                }}
              />
              {/* Line segment below dot, runs to next item */}
              {!isLast && (
                <div
                  style={{
                    width: 1,
                    flex: 1,
                    background: colors.rule,
                    marginTop: 3,
                    marginBottom: 0,
                  }}
                />
              )}
            </div>

            {/* Content */}
            <div
              style={{
                flex: 1,
                minWidth: 0,
                paddingBottom: space.md,
              }}
            >
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
                <span
                  style={{
                    fontFamily: fonts.mono,
                    fontSize: 9,
                    color: colors.textDim,
                  }}
                >
                  [{num}]
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
