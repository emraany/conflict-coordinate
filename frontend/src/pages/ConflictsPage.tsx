import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Brief } from "../components/Brief";
import { ConflictDetailPanel } from "../components/ConflictDetailPanel";
import { colors, fonts, space, statusColor } from "../styles/tokens";
import type { ConflictListItem, ConflictStatus } from "../types";

const SECTION_ORDER: ConflictStatus[] = ["active", "emerging", "frozen", "resolved"];

const SECTION_LABEL: Record<ConflictStatus, string> = {
  active: "ACTIVE",
  emerging: "EMERGING",
  frozen: "FROZEN",
  resolved: "RESOLVED",
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function fmtNum(n: number): string {
  return n === 0 ? "—" : n.toLocaleString();
}

function joinIso3(item: ConflictListItem): string {
  const all = [item.primary_iso3, ...(item.secondary_iso3s ?? [])].filter(
    Boolean,
  ) as string[];
  return all.length ? all.join(" · ") : "—";
}

type SortKey =
  | "name"
  | "event_count"
  | "total_fatalities"
  | "intensity_4w_events"
  | "last_event_at";

function sortConflicts(items: ConflictListItem[], key: SortKey, asc: boolean) {
  return [...items].sort((a, b) => {
    let av: string | number = 0;
    let bv: string | number = 0;
    if (key === "name") { av = a.name; bv = b.name; }
    else if (key === "event_count") { av = a.event_count; bv = b.event_count; }
    else if (key === "total_fatalities") { av = a.total_fatalities; bv = b.total_fatalities; }
    else if (key === "intensity_4w_events") { av = a.intensity_4w_events; bv = b.intensity_4w_events; }
    else if (key === "last_event_at") { av = a.last_event_at ?? ""; bv = b.last_event_at ?? ""; }
    if (av < bv) return asc ? -1 : 1;
    if (av > bv) return asc ? 1 : -1;
    return 0;
  });
}

interface ColDef {
  key: SortKey;
  label: string;
  align: "left" | "right";
}

const SORT_COLS: ColDef[] = [
  { key: "last_event_at", label: "LAST EVENT", align: "left" },
  { key: "intensity_4w_events", label: "4W EVENTS", align: "right" },
  { key: "event_count", label: "EVENTS", align: "right" },
  { key: "total_fatalities", label: "FATALITIES", align: "right" },
];

function StatusSection({
  status,
  items,
  open,
  onToggle,
  sortKey,
  asc,
  onSort,
  onSelect,
}: {
  status: ConflictStatus;
  items: ConflictListItem[];
  open: boolean;
  onToggle: () => void;
  sortKey: SortKey;
  asc: boolean;
  onSort: (k: SortKey) => void;
  onSelect: (slug: string) => void;
}) {
  const sorted = sortConflicts(items, sortKey, asc);
  const accent = statusColor(status);

  function thStyle(align: "left" | "right", active: boolean) {
    return {
      textAlign: align,
      padding: `6px ${align === "right" ? space.md : 0}px 6px 0`,
      fontFamily: fonts.mono,
      fontSize: 9,
      letterSpacing: "0.18em",
      color: active ? colors.oliveLight : colors.textMuted,
      borderBottom: `1px solid ${colors.rule}`,
      cursor: "pointer",
      userSelect: "none" as const,
      whiteSpace: "nowrap" as const,
    };
  }

  return (
    <div style={{ marginBottom: space.xl }}>
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: space.md,
          cursor: "pointer",
          paddingBottom: space.xs,
          borderBottom: `1px solid ${colors.rule}`,
        }}
      >
        <span
          className="label"
          style={{ fontSize: 11, color: accent, letterSpacing: "0.14em" }}
        >
          // {SECTION_LABEL[status]}
        </span>
        <span style={{ fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted }}>
          · {items.length} CONFLICT{items.length !== 1 ? "S" : ""}
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontFamily: fonts.mono,
            fontSize: 9,
            color: colors.textDim,
          }}
        >
          {open ? "▼" : "▶"}
        </span>
      </div>

      {open && (
        <table
          style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}
        >
          <colgroup>
            <col style={{ width: "auto" }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 90 }} />
            <col style={{ width: 100 }} />
          </colgroup>
          <thead>
            <tr>
              {(["NAME", "ISO3"] as const).map((lbl) => (
                <th
                  key={lbl}
                  style={{
                    textAlign: "left",
                    padding: "6px 0",
                    fontFamily: fonts.mono,
                    fontSize: 9,
                    letterSpacing: "0.18em",
                    color: colors.textMuted,
                    borderBottom: `1px solid ${colors.rule}`,
                  }}
                >
                  {lbl}
                </th>
              ))}
              {SORT_COLS.map((col) => (
                <th
                  key={col.key}
                  onClick={() => onSort(col.key)}
                  style={thStyle(col.align, sortKey === col.key)}
                >
                  {col.label}
                  {sortKey === col.key ? (asc ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((c, i) => (
              <tr
                key={c.slug}
                onClick={() => onSelect(c.slug)}
                style={{
                  background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
                  cursor: "pointer",
                  transition: "background 120ms",
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = `color-mix(in srgb, ${colors.oliveLight} 8%, transparent)`)
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)")
                }
              >
                <td
                  style={{
                    padding: "7px 12px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 12,
                    color: colors.text,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.name}
                </td>
                <td
                  style={{
                    padding: "7px 12px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: colors.textMuted,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {joinIso3(c)}
                </td>
                <td
                  style={{
                    padding: "7px 12px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: colors.textMuted,
                  }}
                >
                  {fmt(c.last_event_at)}
                </td>
                <td
                  style={{
                    padding: "7px 16px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: c.intensity_4w_events > 0 ? colors.oliveLight : colors.textDim,
                    textAlign: "right",
                  }}
                >
                  {fmtNum(c.intensity_4w_events)}
                </td>
                <td
                  style={{
                    padding: "7px 16px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: colors.textMuted,
                    textAlign: "right",
                  }}
                >
                  {fmtNum(c.event_count)}
                </td>
                <td
                  style={{
                    padding: "7px 16px 7px 0",
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: c.total_fatalities > 0 ? colors.active : colors.textDim,
                    textAlign: "right",
                  }}
                >
                  {c.total_fatalities > 0 ? `† ${fmtNum(c.total_fatalities)}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

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

export function ConflictsPage() {
  const [conflicts, setConflicts] = useState<ConflictListItem[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeStatuses, setActiveStatuses] = useState<Set<ConflictStatus>>(
    new Set<ConflictStatus>(["active", "emerging", "frozen"]),
  );
  const [typeFilter, setTypeFilter] = useState<string>("__all__");
  const [sortKey, setSortKey] = useState<SortKey>("intensity_4w_events");
  const [sortAsc, setSortAsc] = useState(false);
  const [openSections, setOpenSections] = useState<Set<ConflictStatus>>(
    new Set<ConflictStatus>(["active"]),
  );

  useEffect(() => {
    api.listConflicts().then(setConflicts).catch(console.error);
  }, []);

  function toggleStatus(s: ConflictStatus) {
    setActiveStatuses((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortAsc((a) => !a);
    else {
      setSortKey(key);
      setSortAsc(key === "name");
    }
  }

  const allTypes = useMemo(
    () =>
      [...new Set(conflicts.map((c) => c.conflict_type).filter(Boolean) as string[])].sort(),
    [conflicts],
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return conflicts.filter(
      (c) =>
        activeStatuses.has(c.status) &&
        (typeFilter === "__all__" || c.conflict_type === typeFilter) &&
        (q === "" ||
          c.name.toLowerCase().includes(q) ||
          (c.primary_iso3 ?? "").toLowerCase().includes(q) ||
          c.secondary_iso3s.some((iso) => iso.toLowerCase().includes(q))),
    );
  }, [conflicts, search, activeStatuses, typeFilter]);

  const grouped = useMemo(() => {
    const map = new Map<ConflictStatus, ConflictListItem[]>();
    for (const c of filtered) {
      if (!map.has(c.status)) map.set(c.status, []);
      map.get(c.status)!.push(c);
    }
    return SECTION_ORDER.filter((s) => map.has(s)).map(
      (s) => [s, map.get(s)!] as [ConflictStatus, ConflictListItem[]],
    );
  }, [filtered]);

  function expandAll() {
    setOpenSections(new Set(grouped.map(([s]) => s)));
  }
  function collapseAll() {
    setOpenSections(new Set());
  }
  function toggleSection(s: ConflictStatus) {
    setOpenSections((prev) => {
      const next = new Set(prev);
      next.has(s) ? next.delete(s) : next.add(s);
      return next;
    });
  }

  const totalEvents = conflicts.reduce((s, c) => s + c.event_count, 0);
  const activeCount = conflicts.filter((c) => c.status === "active").length;
  const emergingCount = conflicts.filter((c) => c.status === "emerging").length;

  return (
    <Brief
      section="index"
      rightMeta={
        <>
          <span style={{ color: colors.textMuted }}>{conflicts.length} records</span>
          <span style={{ color: colors.active }}>{activeCount} active</span>
          {emergingCount > 0 && (
            <span style={{ color: colors.amberReserved }}>
              {emergingCount} emerging
            </span>
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
          <span
            className="stamp"
            style={{ fontSize: 14, letterSpacing: "0.22em", color: colors.text }}
          >
            CONFLICT INDEX
          </span>
          <span
            style={{
              fontFamily: fonts.mono,
              fontSize: 10,
              color: colors.textMuted,
              letterSpacing: "0.1em",
            }}
          >
            {totalEvents.toLocaleString()} DOCUMENTED EVENTS
          </span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.lg,
            marginBottom: space.md,
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
              placeholder="name or iso3..."
              style={{
                background: colors.bgSunken,
                border: `1px solid ${colors.rule}`,
                color: colors.text,
                fontFamily: fonts.mono,
                fontSize: 11,
                padding: "4px 10px",
                outline: "none",
                width: 220,
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span className="label" style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em" }}>
              STATUS
            </span>
            {(["active", "emerging", "frozen", "resolved"] as ConflictStatus[]).map((s) => {
              const on = activeStatuses.has(s);
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

          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span className="label" style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em" }}>
              TYPE
            </span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              style={{
                background: colors.bgSunken,
                border: `1px solid ${colors.rule}`,
                color: typeFilter === "__all__" ? colors.textMuted : colors.oliveLight,
                fontFamily: fonts.mono,
                fontSize: 11,
                padding: "4px 10px",
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="__all__">ALL TYPES</option>
              {allTypes.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, " ").toUpperCase()}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: "flex", gap: space.sm, marginBottom: space.xl }}>
          <button onClick={expandAll} style={monoBtn}>
            [ EXPAND ALL ]
          </button>
          <button onClick={collapseAll} style={monoBtn}>
            [ COLLAPSE ALL ]
          </button>
        </div>

        {grouped.length === 0 ? (
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 12,
              color: colors.textMuted,
              marginTop: space.xl,
            }}
          >
            // NO RECORDS MATCH CURRENT FILTER
          </div>
        ) : (
          grouped.map(([status, items]) => (
            <StatusSection
              key={status}
              status={status}
              items={items}
              open={openSections.has(status)}
              onToggle={() => toggleSection(status)}
              sortKey={sortKey}
              asc={sortAsc}
              onSort={handleSort}
              onSelect={setSelectedSlug}
            />
          ))
        )}
      </div>
    </Brief>
  );
}
