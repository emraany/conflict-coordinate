/**
 * Presentational primitives shared by the region dossier (a globe dot) and
 * the conflict dossier (a named storyline). Extracted so both read as the
 * same document rather than drifting apart.
 */
import { colors, fonts, space } from "../../styles/tokens";
import type { IntensityWeek } from "../../types";

export function formatYmd(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

export function formatMonth(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en", { month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

export function formatDuration(
  start: string | null,
  end: string | null,
  isActive: boolean,
): string {
  if (!start) return "—";
  const s = new Date(start).getTime();
  if (!Number.isFinite(s)) return "—";
  const endMs = isActive ? Date.now() : end ? new Date(end).getTime() : Date.now();
  const months = Math.max(0, Math.round((endMs - s) / (1000 * 60 * 60 * 24 * 30.4375)));
  if (months < 1) return "< 1 mo";
  if (months < 12) return `${months} mo`;
  const yrs = Math.floor(months / 12);
  const mo = months % 12;
  return mo === 0 ? `${yrs} yr${yrs === 1 ? "" : "s"}` : `${yrs} yr · ${mo} mo`;
}

export function SectionHeader({
  id,
  num,
  stamp,
  subline,
  count,
}: {
  id: string;
  num: string;
  stamp: string;
  subline: string;
  count?: number;
}) {
  return (
    <div
      id={id}
      style={{
        scrollMarginTop: 56,
        paddingBottom: space.sm,
        marginBottom: space.md,
        borderBottom: `1px solid ${colors.ruleStrong}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: space.sm }}>
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 10,
            color: colors.textDim,
            letterSpacing: "0.12em",
          }}
        >
          [{num}]
        </span>
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 13,
            color: colors.text,
            letterSpacing: "0.16em",
            fontWeight: 600,
          }}
        >
          {stamp}
        </span>
        {typeof count === "number" && (
          <span
            style={{
              fontFamily: fonts.mono,
              fontSize: 10,
              color: colors.textMuted,
              marginLeft: "auto",
            }}
          >
            [{String(count).padStart(2, "0")}]
          </span>
        )}
      </div>
      <div
        className="serif"
        style={{
          marginTop: 4,
          fontSize: 13,
          color: colors.textMuted,
          fontStyle: "italic",
          lineHeight: 1.5,
        }}
      >
        {subline}
      </div>
    </div>
  );
}

export function SubHeader({
  stamp,
  subline,
  count,
}: {
  stamp: string;
  subline: string;
  count?: number;
}) {
  return (
    <div style={{ marginBottom: space.sm }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: space.sm }}>
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 11,
            color: colors.oliveLight,
            letterSpacing: "0.14em",
            fontWeight: 600,
          }}
        >
          {stamp}
        </span>
        {typeof count === "number" && (
          <span
            style={{ fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted }}
          >
            [{String(count).padStart(2, "0")}]
          </span>
        )}
      </div>
      <div
        className="serif"
        style={{ fontSize: 12, color: colors.textDim, fontStyle: "italic" }}
      >
        {subline}
      </div>
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div
      style={{
        flex: "1 1 140px",
        minWidth: 0,
        background: colors.bgRaised,
        border: `1px solid ${colors.rule}`,
        padding: `${space.sm}px ${space.md}px`,
      }}
    >
      <div
        className="label"
        style={{
          fontSize: 9,
          color: colors.textMuted,
          letterSpacing: "0.18em",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 22,
          color: colors.text,
          letterSpacing: "0.02em",
          lineHeight: 1.1,
          fontWeight: 500,
        }}
      >
        {value}
      </div>
      {hint && (
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 9,
            color: colors.textDim,
            marginTop: 3,
            letterSpacing: "0.04em",
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

export function IntensitySparkline({
  weeks,
  caption,
}: {
  weeks: IntensityWeek[];
  caption: string;
}) {
  if (weeks.length === 0) return null;
  const counts = weeks.map((w) =>
    Object.values(w.event_count_by_type).reduce((a, b) => a + b, 0),
  );
  const max = Math.max(...counts, 1);
  const W = 4;
  const GAP = 2;
  const H = 28;
  const totalW = counts.length * (W + GAP) - GAP;
  const first = weeks[0]?.week_start;
  const last = weeks[weeks.length - 1]?.week_start;
  return (
    <div style={{ marginBottom: space.md }}>
      <svg
        viewBox={`0 0 ${totalW} ${H}`}
        preserveAspectRatio="none"
        style={{ width: "100%", height: H, display: "block" }}
        aria-hidden
      >
        {counts.map((c, i) => {
          const h = c === 0 ? 1 : Math.max(2, (c / max) * H);
          return (
            <rect
              key={i}
              x={i * (W + GAP)}
              y={H - h}
              width={W}
              height={h}
              fill={c === 0 ? colors.rule : colors.oliveLight}
            />
          );
        })}
      </svg>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontFamily: fonts.mono,
          fontSize: 9,
          color: colors.textDim,
          letterSpacing: "0.12em",
          marginTop: 2,
        }}
      >
        <span>{first ?? "—"}</span>
        <span>{caption}</span>
        <span>{last ?? "—"}</span>
      </div>
    </div>
  );
}

export function EventTypeBreakdown({ weeks }: { weeks: IntensityWeek[] }) {
  const tail = weeks.slice(-4);
  if (tail.length === 0) return null;
  const totals = new Map<string, number>();
  for (const w of tail) {
    for (const [type, n] of Object.entries(w.event_count_by_type)) {
      totals.set(type, (totals.get(type) ?? 0) + n);
    }
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  if (ranked.length === 0) return null;
  const max = ranked[0][1];
  return (
    <div style={{ marginBottom: space.md }}>
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 10,
          color: colors.textDim,
          letterSpacing: "0.12em",
          marginBottom: 6,
        }}
      >
        BREAKDOWN — LAST 4 WEEKS
      </div>
      {ranked.map(([type, count]) => (
        <div
          key={type}
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.sm,
            marginBottom: 3,
          }}
        >
          <div
            style={{
              flex: "0 0 180px",
              fontFamily: fonts.mono,
              fontSize: 11,
              color: colors.text,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {type}
          </div>
          <div
            style={{
              flex: 1,
              height: 8,
              background: colors.bgSunken,
              border: `1px solid ${colors.rule}`,
            }}
          >
            <div
              style={{
                width: `${(count / max) * 100}%`,
                height: "100%",
                background: colors.oliveLight,
              }}
            />
          </div>
          <div
            style={{
              flex: "0 0 32px",
              textAlign: "right",
              fontFamily: fonts.mono,
              fontSize: 11,
              color: colors.textMuted,
            }}
          >
            {count}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Dated situation-report excerpts — the dossier's current narrative. */
export function FieldReportList({
  reports,
}: {
  reports: Array<{
    id: number;
    title: string;
    url: string;
    publisher: string | null;
    published_at: string | null;
    body_text: string | null;
  }>;
}) {
  if (reports.length === 0) {
    return (
      <p
        className="serif"
        style={{
          margin: 0,
          fontSize: 13,
          color: colors.textMuted,
          fontStyle: "italic",
          lineHeight: 1.6,
        }}
      >
        No recent situation reports on file for this country.
      </p>
    );
  }
  return (
    <ol style={{ margin: 0, padding: 0, listStyle: "none" }}>
      {reports.map((r, i) => (
        <li
          key={r.id}
          style={{
            paddingBottom: space.md,
            marginBottom: space.md,
            borderBottom:
              i === reports.length - 1 ? "none" : `1px dashed ${colors.rule}`,
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
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: colors.text,
                fontFamily: fonts.mono,
                fontSize: 13,
                flex: 1,
                minWidth: 0,
                wordBreak: "break-word",
              }}
            >
              {r.title}
            </a>
            <span
              style={{
                fontFamily: fonts.mono,
                fontSize: 10,
                color: colors.textMuted,
                flexShrink: 0,
              }}
            >
              {[r.publisher, formatYmd(r.published_at)].filter(Boolean).join(" · ")}
            </span>
          </div>
          {r.body_text && (
            <p
              className="serif"
              style={{
                margin: `${space.xs}px 0 0 0`,
                fontSize: 13,
                lineHeight: 1.65,
                color: colors.textMuted,
              }}
            >
              {r.body_text}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
