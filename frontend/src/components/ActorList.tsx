import { useState } from "react";

import { colors, fonts, space } from "../styles/tokens";
import type { ActorLink, Source } from "../types";

interface Props {
  actors: ActorLink[];
  sources: Source[];
}

function sourceRefNumber(sources: Source[], sourceId: number | null): number | null {
  if (sourceId === null) return null;
  const idx = sources.findIndex((s) => s.id === sourceId);
  return idx >= 0 ? idx + 1 : null;
}

function roleLabel(role: string): string {
  switch (role) {
    case "party":
      return "Party";
    case "mediator":
      return "Mediator";
    case "observer":
      return "Observer";
    case "affected":
      return "Affected";
    default:
      return role;
  }
}

export function ActorList({ actors, sources }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (actors.length === 0) {
    return (
      <div className="label" style={{ color: colors.textDim }}>
        (no actors recorded)
      </div>
    );
  }

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
      {actors.map((link, i) => {
        const ref = sourceRefNumber(sources, link.source_id);
        const num = String(i + 1).padStart(2, "0");
        const description = link.actor.description?.trim() || null;
        const isOpen = expanded.has(link.actor.id);

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
          descStyle.WebkitLineClamp = 3;
          descStyle.overflow = "hidden";
        }

        return (
          <li
            key={`${link.actor.id}-${i}`}
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
                  justifyContent: "space-between",
                  gap: space.md,
                  alignItems: "baseline",
                }}
              >
                <span style={{ color: colors.text, display: "flex", alignItems: "baseline", gap: space.xs, flexWrap: "wrap" }}>
                  {link.actor.name}
                  {link.actor.wikipedia_url && (
                    <a
                      href={link.actor.wikipedia_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Wikipedia"
                      style={{
                        fontFamily: fonts.mono,
                        fontSize: 9,
                        letterSpacing: "0.16em",
                        color: colors.oliveLight,
                        border: `1px solid ${colors.oliveDim}`,
                        padding: "0 4px",
                        textDecoration: "none",
                      }}
                    >
                      [W]
                    </a>
                  )}
                </span>
                <span
                  className="label"
                  style={{ fontSize: 10, color: colors.oliveLight }}
                >
                  {roleLabel(link.role)}
                </span>
              </div>
              <div
                className="label"
                style={{ marginTop: 2, fontSize: 10, color: colors.textMuted }}
              >
                {link.actor.type.replace("_", " ")}
                {ref !== null && (
                  <>
                    {" · "}
                    <span style={{ color: colors.textMuted }}>
                      cited in src §{String(ref).padStart(2, "0")}
                    </span>
                  </>
                )}
              </div>
              {description && (
                <p
                  className="serif"
                  onClick={() => toggle(link.actor.id)}
                  style={descStyle}
                >
                  {description}
                </p>
              )}
              {link.notes && (
                <div
                  style={{
                    marginTop: 4,
                    fontSize: 12,
                    color: colors.textMuted,
                  }}
                >
                  {link.notes}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
