import { useEffect, useMemo, useState } from "react";
import { Brief } from "../components/Brief";
import { ConflictDetailPanel } from "../components/ConflictDetailPanel";
import { StatusChip } from "../components/StatusChip";
import { colors, fonts, space, statusColor } from "../styles/tokens";
import type { ConflictStatus } from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

type Window = "24h" | "7d" | "30d";

const WINDOWS: { key: Window; label: string; days: number }[] = [
  { key: "24h", label: "24H", days: 1 },
  { key: "7d", label: "7D", days: 7 },
  { key: "30d", label: "30D", days: 30 },
];

function fmtType(t: string | null): string {
  if (!t) return "—";
  return t.replace(/_/g, " ").toUpperCase();
}

interface ActivityItem {
  id: number;
  occurred_at: string;
  event_type: string | null;
  description: string | null;
  fatalities: number | null;
  location_name: string | null;
  conflict_slug: string;
  conflict_name: string;
  conflict_primary_iso3: string | null;
  conflict_status: ConflictStatus;
  conflict_type: string | null;
}

function sinceISO(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString();
}

function dateLabel(iso: string): string {
  return iso.slice(0, 10);
}

function timeLabel(iso: string): string {
  return new Date(iso).toISOString().slice(11, 16);
}

const COL_HEADER_STYLE = {
  fontFamily: fonts.mono,
  fontSize: 9,
  letterSpacing: "0.18em",
  color: colors.textMuted,
  borderBottom: `1px solid ${colors.rule}`,
  padding: "5px 12px 5px 0",
  textAlign: "left" as const,
  whiteSpace: "nowrap" as const,
};

const monoBtn = {
  background: "none",
  border: `1px solid ${colors.rule}`,
  color: colors.textMuted,
  fontFamily: fonts.mono,
  fontSize: 10,
  letterSpacing: "0.16em",
  padding: "3px 10px",
  cursor: "pointer",
} as const;

export function ActivityPage() {
  const [window, setWindow] = useState<Window>("7d");
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilters, setStatusFilters] = useState<Set<ConflictStatus>>(
    new Set<ConflictStatus>(["active", "emerging", "frozen"]),
  );

  useEffect(() => {
    const days = WINDOWS.find((w) => w.key === window)!.days;
    setLoading(true);
    fetch(`${API_URL}/api/activity?since=${sinceISO(days)}&limit=1000`)
      .then((r) => r.json())
      .then((d) => { setItems(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [window]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (!statusFilters.has(item.conflict_status)) return false;
      if (q === "") return true;
      return (
        item.conflict_name.toLowerCase().includes(q) ||
        (item.location_name ?? "").toLowerCase().includes(q) ||
        (item.conflict_primary_iso3 ?? "").toLowerCase().includes(q)
      );
    });
  }, [items, search, statusFilters]);

  function toggleStatus(s: ConflictStatus) {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  const totalFatalities = filtered.reduce((s, i) => s + (i.fatalities ?? 0), 0);

  return (
    <Brief
      section="activity"
      rightMeta={
        <>
          <span style={{ color: colors.textMuted }}>{filtered.length} events</span>
          {totalFatalities > 0 && (
            <span style={{ color: colors.active }}>† {totalFatalities.toLocaleString()}</span>
          )}
          <a href="/admin" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /admin
          </a>
        </>
      }
    >
      <ConflictDetailPanel slug={selectedSlug} onClose={() => setSelectedSlug(null)} />

      <div style={{ height: "100%", overflowY: "auto", padding: `${space.lg}px ${space.xl}px` }}>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: space.lg,
            borderBottom: `1px solid ${colors.rule}`,
            paddingBottom: space.sm,
          }}
        >
          <span className="stamp" style={{ fontSize: 14, letterSpacing: "0.22em", color: colors.text }}>
            RECENT ACTIVITY
          </span>
          <div style={{ display: "flex", gap: space.sm }}>
            {WINDOWS.map((w) => {
              const active = w.key === window;
              return (
                <button
                  key={w.key}
                  onClick={() => setWindow(w.key)}
                  style={{
                    background: active ? colors.oliveDim : "transparent",
                    border: `1px solid ${active ? colors.olive : colors.rule}`,
                    color: active ? colors.oliveLight : colors.textMuted,
                    fontFamily: fonts.mono,
                    fontSize: 10,
                    letterSpacing: "0.16em",
                    padding: "3px 12px",
                    cursor: "pointer",
                    transition: "all 150ms",
                  }}
                >
                  [ {w.label} ]
                </button>
              );
            })}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.lg,
            marginBottom: space.lg,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span className="label" style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em" }}>
              SEARCH
            </span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="conflict, location, iso3..."
              style={{
                background: colors.bgSunken,
                border: `1px solid ${colors.rule}`,
                color: colors.text,
                fontFamily: fonts.mono,
                fontSize: 11,
                padding: "4px 10px",
                outline: "none",
                width: 260,
              }}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span className="label" style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em" }}>
              STATUS
            </span>
            {(["active", "emerging", "frozen"] as ConflictStatus[]).map((s) => {
              const on = statusFilters.has(s);
              const c = statusColor(s);
              return (
                <button
                  key={s}
                  onClick={() => toggleStatus(s)}
                  style={{
                    background: on ? `color-mix(in srgb, ${c} 12%, ${colors.bg})` : "transparent",
                    border: `1px solid ${on ? c : colors.rule}`,
                    color: on ? c : colors.textDim,
                    fontFamily: fonts.mono,
                    fontSize: 10,
                    letterSpacing: "0.18em",
                    padding: "3px 10px",
                    cursor: "pointer",
                    transition: "all 150ms",
                  }}
                >
                  [ {s.toUpperCase()} ]
                </button>
              );
            })}
          </div>
        </div>

        {loading && (
          <div style={{ fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted }}>
            // FETCHING...
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div style={{ fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted }}>
            // NO EVENTS IN THIS WINDOW
          </div>
        )}

        {filtered.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 76 }} />
              <col style={{ width: 52 }} />
              <col style={{ width: "auto" }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 170 }} />
              <col style={{ width: 60 }} />
            </colgroup>
            <thead>
              <tr>
                <th style={COL_HEADER_STYLE}>DATE</th>
                <th style={COL_HEADER_STYLE}>TIME</th>
                <th style={COL_HEADER_STYLE}>CONFLICT</th>
                <th style={COL_HEADER_STYLE}>STATUS</th>
                <th style={COL_HEADER_STYLE}>TYPE</th>
                <th style={COL_HEADER_STYLE}>LOCATION</th>
                <th style={{ ...COL_HEADER_STYLE, textAlign: "right", paddingRight: space.md }}>FAT.</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, i) => (
                <tr
                  key={item.id}
                  onClick={() => setSelectedSlug(item.conflict_slug)}
                  style={{
                    background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                    cursor: "pointer",
                    transition: "background 120ms",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = `color-mix(in srgb, ${colors.oliveLight} 7%, transparent)`)
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)")
                  }
                >
                  <td style={{ padding: "6px 12px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                    {dateLabel(item.occurred_at)}
                  </td>
                  <td style={{ padding: "6px 12px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                    {timeLabel(item.occurred_at)}
                  </td>
                  <td style={{ padding: "6px 12px 6px 0", fontFamily: fonts.mono, fontSize: 12, color: colors.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.conflict_name}
                  </td>
                  <td style={{ padding: "6px 12px 6px 0" }}>
                    <StatusChip status={item.conflict_status} />
                  </td>
                  <td style={{ padding: "6px 12px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {fmtType(item.conflict_type)}
                  </td>
                  <td style={{ padding: "6px 12px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.location_name ?? "—"}
                  </td>
                  <td style={{ padding: "6px 16px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: (item.fatalities ?? 0) > 0 ? colors.active : colors.textDim, textAlign: "right" }}>
                    {(item.fatalities ?? 0) > 0 ? `† ${item.fatalities}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div style={{ marginTop: space.xl, display: "flex", gap: space.sm }}>
          <button onClick={() => setSearch("")} style={monoBtn}>
            [ CLEAR FILTERS ]
          </button>
        </div>
      </div>
    </Brief>
  );
}
