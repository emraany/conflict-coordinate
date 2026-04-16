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
  if (actors.length === 0) {
    return (
      <div className="label" style={{ color: colors.textDim }}>
        (no actors recorded)
      </div>
    );
  }

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
            <div style={{ flex: 1 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: space.md,
                  alignItems: "baseline",
                }}
              >
                <span style={{ color: colors.text }}>{link.actor.name}</span>
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
