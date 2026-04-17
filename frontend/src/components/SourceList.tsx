import { colors, fonts, space } from "../styles/tokens";
import type { Source } from "../types";

interface Props {
  sources: Source[];
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

function originLabel(origin: string | null): string {
  if (!origin) return "CURATED";
  return origin.toUpperCase();
}

export function SourceList({ sources }: Props) {
  if (sources.length === 0) {
    return (
      <div className="label" style={{ color: colors.textDim }}>
        (no sources recorded)
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
      {sources.map((s, i) => {
        const num = String(i + 1).padStart(2, "0");
        const date = formatDate(s.published_at);
        return (
          <li
            key={s.id}
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
              §{num}
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
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    color: colors.text,
                    wordBreak: "break-word",
                    flex: 1,
                  }}
                >
                  {s.title}
                </a>
                <span
                  style={{
                    fontFamily: fonts.mono,
                    fontSize: 9,
                    letterSpacing: "0.16em",
                    color: colors.oliveLight,
                    background: colors.bgSunken,
                    border: `1px solid ${colors.oliveDim}`,
                    padding: "1px 6px",
                    flexShrink: 0,
                  }}
                >
                  [{originLabel(s.origin)}]
                </span>
              </div>
              <div
                className="label"
                style={{ marginTop: 2, fontSize: 10, color: colors.textMuted }}
              >
                {[s.publisher, s.source_type, date].filter(Boolean).join(" · ")}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
