import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { colors, fonts, space } from "../styles/tokens";
import type {
  ActorLink,
  ActorRole,
  CrisisDetail,
  CrisisEntities,
  CrisisEvent,
  IntensityWeek,
} from "../types";
import { ActorList } from "./ActorList";
import { EventTimeline } from "./EventTimeline";
import { RelationshipsSection } from "./RelationshipsSection";
import { SourceList } from "./SourceList";
import { StatusChip } from "./StatusChip";

interface Props {
  slug: string | null;
  onClose: () => void;
}

const ROLE_GROUPS: Array<{ role: ActorRole; label: string; subline: string }> = [
  { role: "party", label: "PARTIES", subline: "actively engaged in the conflict" },
  { role: "mediator", label: "MEDIATORS", subline: "external parties working toward resolution" },
  { role: "observer", label: "OBSERVERS", subline: "monitoring without taking sides" },
  { role: "affected", label: "AFFECTED", subline: "civilian populations bearing the brunt" },
];

const NAME_SUPERGROUPS: Array<{
  key: string;
  label: string;
  subline: string;
  ner: string[];
}> = [
  { key: "people", label: "PEOPLE", subline: "individuals named in coverage", ner: ["PERSON"] },
  {
    key: "groups",
    label: "GROUPS & ORGANIZATIONS",
    subline: "named groups, agencies, and movements",
    ner: ["ORG", "NORP"],
  },
  {
    key: "places",
    label: "PLACES",
    subline: "countries, cities, regions, and facilities",
    ner: ["GPE", "LOC", "FAC", "EVENT"],
  },
];

const SECTION_NAV: Array<{ id: string; num: string; label: string }> = [
  { id: "cc-glance", num: "01", label: "GLANCE" },
  { id: "cc-who", num: "02", label: "WHO" },
  { id: "cc-when", num: "03", label: "TIMELINE" },
  { id: "cc-where", num: "04", label: "WHERE" },
  { id: "cc-names", num: "05", label: "NAMES" },
  { id: "cc-network", num: "06", label: "NETWORK" },
  { id: "cc-sources", num: "07", label: "SOURCES" },
];

function formatYmd(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

function formatDuration(start: string | null, end: string | null, isActive: boolean): string {
  if (!start) return "—";
  const s = new Date(start).getTime();
  if (!Number.isFinite(s)) return "—";
  const endMs = isActive ? Date.now() : end ? new Date(end).getTime() : Date.now();
  const months = Math.max(0, Math.round((endMs - s) / (1000 * 60 * 60 * 24 * 30.4375)));
  if (months < 1) return "< 1 mo";
  if (months < 12) return `${months} mo`;
  const yrs = Math.floor(months / 12);
  const mo = months % 12;
  return mo === 0
    ? `${yrs} yr${yrs === 1 ? "" : "s"}`
    : `${yrs} yr · ${mo} mo`;
}

function topLocations(
  events: CrisisEvent[],
  limit = 8,
): Array<{ name: string; count: number }> {
  const counts = new Map<string, number>();
  for (const ev of events) {
    const name = ev.location_name?.trim();
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([name, count]) => ({ name, count }));
}

function SectionHeader({
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

function SubHeader({
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
            style={{
              fontFamily: fonts.mono,
              fontSize: 10,
              color: colors.textMuted,
            }}
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

function StatTile({ label, value }: { label: string; value: string }) {
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
    </div>
  );
}

function IntensitySparkline({ weeks }: { weeks: IntensityWeek[] }) {
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
        <span>WEEKLY EVENT COUNT — ACLED AGGREGATES</span>
        <span>{last ?? "—"}</span>
      </div>
    </div>
  );
}

function EventTypeBreakdown({ weeks }: { weeks: IntensityWeek[] }) {
  // Top event-types by total events in the last 4 weeks (or full window if
  // < 4 weeks present).
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

function formatCompact(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

function formatMonth(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en", { month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

function NameChip({ text, count }: { text: string; count: number }) {
  return (
    <span
      style={{
        fontFamily: fonts.mono,
        fontSize: 11,
        color: colors.text,
        background: colors.bgSunken,
        border: `1px solid ${colors.rule}`,
        padding: "2px 6px",
        whiteSpace: "nowrap",
      }}
    >
      {text} <span style={{ color: colors.textDim }}>×{count}</span>
    </span>
  );
}

export function CrisisDetailPanel({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<CrisisDetail | null>(null);
  const [entities, setEntities] = useState<CrisisEntities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAllParties, setShowAllParties] = useState(false);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setShowAllParties(false);
    setShowAllTimeline(false);
    setEntities(null);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getCrisis(slug)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(e.status === 404 ? "Not found" : `Error ${e.status}`);
        } else {
          setError("Error loading crisis");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    api
      .getCrisisEntities(slug)
      .then((d) => {
        if (!cancelled) setEntities(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const sourceIndex = useMemo(() => {
    const idx = new Map<number, number>();
    if (!detail) return idx;
    detail.sources.forEach((s, i) => idx.set(s.id, i + 1));
    return idx;
  }, [detail]);

  const locations = useMemo(
    () => (detail ? topLocations(detail.events, 8) : []),
    [detail],
  );

  const actorsByRole = useMemo(() => {
    const map = new Map<ActorRole, ActorLink[]>();
    if (!detail) return map;
    for (const link of detail.actors) {
      const arr = map.get(link.role) ?? [];
      arr.push(link);
      map.set(link.role, arr);
    }
    return map;
  }, [detail]);

  const namesBySupergroup = useMemo(() => {
    const out = new Map<string, Array<{ text: string; count: number }>>();
    if (!entities) return out;
    for (const sg of NAME_SUPERGROUPS) {
      const merged: Array<{ text: string; count: number }> = [];
      for (const g of entities.groups) {
        if (sg.ner.includes(g.label)) {
          for (const e of g.entities) merged.push({ text: e.text, count: e.count });
        }
      }
      merged.sort((a, b) => b.count - a.count);
      out.set(sg.key, merged.slice(0, 12));
    }
    return out;
  }, [entities]);

  if (!slug) return null;

  const handleJump = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <aside
      style={{
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        animation: "cc-fade-in 180ms cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <style>{`
        @keyframes cc-fade-in {
          from { opacity: 0; transform: translateX(8px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>

      {/* MASTHEAD */}
      <div
        style={{
          padding: `${space.md}px ${space.lg}px`,
          borderBottom: `1px solid ${colors.rule}`,
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: space.md,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: fonts.stamp,
              fontSize: 22,
              letterSpacing: "0.04em",
              color: colors.text,
              lineHeight: 1.15,
            }}
          >
            {detail?.name ?? (loading ? "LOADING…" : slug)}
          </div>
          {detail && (
            <div
              style={{
                marginTop: space.sm,
                display: "flex",
                alignItems: "center",
                gap: space.sm,
                fontFamily: fonts.mono,
                fontSize: 12,
                color: colors.textMuted,
                flexWrap: "wrap",
              }}
            >
              <StatusChip status={detail.status} />
              <span style={{ color: colors.text }}>
                {detail.admin1 ? `${detail.admin1}, ` : ""}
                {detail.country ?? "—"}
              </span>
              <span style={{ color: colors.textDim }}>·</span>
              <span>{detail.region ?? "unspecified region"}</span>
              {detail.conflict_type && (
                <>
                  <span style={{ color: colors.textDim }}>·</span>
                  <span>{detail.conflict_type}</span>
                </>
              )}
              <span style={{ color: colors.textDim }}>·</span>
              <span>
                {detail.status === "active"
                  ? "active — events this month"
                  : detail.status === "frozen"
                    ? `dormant — last activity ${formatMonth(detail.last_event_at)}`
                    : `last activity ${formatYmd(detail.last_event_at)}`}
              </span>
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            fontSize: 20,
            lineHeight: 1,
            color: colors.textMuted,
            background: "none",
            border: 0,
            padding: `0 ${space.xs}px`,
            cursor: "pointer",
          }}
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* SCROLL AREA */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto" }}>
        {detail && (
          <div
            style={{
              position: "sticky",
              top: 0,
              zIndex: 1,
              background: colors.bg,
              borderBottom: `1px solid ${colors.rule}`,
              padding: `${space.xs}px ${space.lg}px`,
              display: "flex",
              flexWrap: "wrap",
              gap: `${space.xs}px ${space.md}px`,
            }}
          >
            {SECTION_NAV.map((s) => (
              <button
                key={s.id}
                onClick={() => handleJump(s.id)}
                style={{
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  fontFamily: fonts.mono,
                  fontSize: 10,
                  color: colors.textMuted,
                  letterSpacing: "0.12em",
                }}
              >
                <span style={{ color: colors.textDim }}>§{s.num}</span>{" "}
                <span>{s.label}</span>
              </button>
            ))}
          </div>
        )}

        <div style={{ padding: `${space.lg}px ${space.lg}px ${space.xl}px` }}>
          {error && (
            <div style={{ color: colors.active }}>
              <span className="stamp">ERROR</span> — {error}
            </div>
          )}

          {detail && (
            <>
              {/* 01 AT A GLANCE */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-glance"
                  num="01"
                  stamp="AT A GLANCE"
                  subline="the conflict in three numbers and a paragraph"
                />
                <div
                  style={{
                    display: "flex",
                    gap: space.sm,
                    marginBottom: space.md,
                    flexWrap: "wrap",
                  }}
                >
                  <StatTile
                    label="DURATION"
                    value={formatDuration(
                      detail.started_at,
                      detail.last_event_at,
                      detail.status === "active",
                    )}
                  />
                  <StatTile
                    label="EVENTS · LAST 4 WEEKS"
                    value={(detail.stats.recent_4w_events ?? 0).toLocaleString()}
                  />
                  <StatTile
                    label="FATALITIES · LAST 4 WEEKS"
                    value={(detail.stats.recent_4w_fatalities ?? 0).toLocaleString()}
                  />
                  {detail.stats.recent_population_exposed != null && (
                    <StatTile
                      label="POP. EXPOSED · 4W (MAX)"
                      value={formatCompact(detail.stats.recent_population_exposed)}
                    />
                  )}
                  <StatTile
                    label="TOTAL INCIDENTS ON FILE"
                    value={detail.stats.total_events.toLocaleString()}
                  />
                </div>
                {detail.intensity_52w.length > 0 && (
                  <>
                    <IntensitySparkline weeks={detail.intensity_52w} />
                    <EventTypeBreakdown weeks={detail.intensity_52w} />
                  </>
                )}
                {detail.summary ? (
                  <p
                    className="serif"
                    style={{
                      margin: 0,
                      fontSize: 14,
                      lineHeight: 1.7,
                      color: colors.text,
                    }}
                  >
                    {detail.summary}
                  </p>
                ) : (
                  <p
                    className="label"
                    style={{
                      margin: 0,
                      fontSize: 11,
                      color: colors.textDim,
                      fontStyle: "italic",
                    }}
                  >
                    No background summary on file.
                  </p>
                )}
              </section>

              {/* 02 WHO IS INVOLVED */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-who"
                  num="02"
                  stamp="WHO IS INVOLVED"
                  subline="the sides of the conflict, who is mediating, and who is caught in the middle"
                  count={detail.actors.length}
                />
                {detail.actors.length === 0 ? (
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
                    No actor records yet for this admin1. ACLED's event-level
                    feed runs ~12 months behind the weekly aggregates above;
                    parties will populate as those records catch up.
                  </p>
                ) : (
                  <>
                    {ROLE_GROUPS.map((rg) => {
                      const actors = actorsByRole.get(rg.role) ?? [];
                      if (actors.length === 0) return null;
                      const PREVIEW = 5;
                      const visible = showAllParties
                        ? actors
                        : actors.slice(0, PREVIEW);
                      return (
                        <div key={rg.role} style={{ marginBottom: space.md }}>
                          <SubHeader
                            stamp={rg.label}
                            subline={rg.subline}
                            count={actors.length}
                          />
                          <ActorList actors={visible} sourceIndex={sourceIndex} />
                        </div>
                      );
                    })}
                    {detail.actors.length > 5 && (
                      <button
                        onClick={() => setShowAllParties((v) => !v)}
                        style={{
                          background: "none",
                          border: "none",
                          padding: `${space.xs}px 0`,
                          cursor: "pointer",
                          fontFamily: fonts.mono,
                          fontSize: 11,
                          color: colors.oliveLight,
                          letterSpacing: "0.1em",
                        }}
                      >
                        {showAllParties
                          ? "[ collapse ]"
                          : `[ show all ${detail.actors.length} ]`}
                      </button>
                    )}
                  </>
                )}
              </section>

              {/* 03 HOW IT'S UNFOLDING */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-when"
                  num="03"
                  stamp="HOW IT'S UNFOLDING"
                  subline="individual incidents recorded for this admin1 — sourced from ACLED, UCDP, and GDELT"
                  count={detail.events.length}
                />
                {detail.events.length === 0 ? (
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
                    Activity is recorded in the weekly aggregates above, but
                    no individual incident records have been attached yet.
                    Detailed events populate as the ACLED API window
                    advances and UCDP/GDELT feeds match this admin1.
                  </p>
                ) : (
                  (() => {
                    const TIMELINE_LIMIT = 10;
                    const visible = showAllTimeline
                      ? detail.events
                      : detail.events.slice(0, TIMELINE_LIMIT);
                    const hidden = detail.events.length - visible.length;
                    return (
                      <>
                        <EventTimeline
                          events={visible}
                          sourceIndex={sourceIndex}
                        />
                        {(hidden > 0 || showAllTimeline) && (
                          <button
                            onClick={() => setShowAllTimeline((v) => !v)}
                            style={{
                              background: "none",
                              border: "none",
                              padding: `${space.xs}px 0`,
                              cursor: "pointer",
                              fontFamily: fonts.mono,
                              fontSize: 11,
                              color: colors.oliveLight,
                              letterSpacing: "0.1em",
                            }}
                          >
                            {showAllTimeline
                              ? "[ collapse ]"
                              : `[ show all ${detail.events.length} ]`}
                          </button>
                        )}
                      </>
                    );
                  })()
                )}
              </section>

              {/* 04 WHERE IT'S HAPPENING */}
              {locations.length > 0 && (
                <section style={{ marginBottom: space.xl }}>
                  <SectionHeader
                    id="cc-where"
                    num="04"
                    stamp="WHERE IT'S HAPPENING"
                    subline="the towns and provinces seeing the most activity"
                    count={locations.length}
                  />
                  <ol
                    style={{
                      margin: 0,
                      padding: 0,
                      listStyle: "none",
                    }}
                  >
                    {locations.map((loc, i) => (
                      <li
                        key={loc.name}
                        style={{
                          display: "flex",
                          alignItems: "baseline",
                          gap: space.md,
                          paddingTop: space.xs,
                          paddingBottom: space.xs,
                          borderBottom:
                            i === locations.length - 1
                              ? "none"
                              : `1px dashed ${colors.rule}`,
                        }}
                      >
                        <span
                          style={{
                            fontFamily: fonts.mono,
                            fontSize: 11,
                            color: colors.textDim,
                            minWidth: 28,
                          }}
                        >
                          [{String(i + 1).padStart(2, "0")}]
                        </span>
                        <span
                          style={{
                            flex: 1,
                            fontFamily: fonts.mono,
                            fontSize: 13,
                            color: colors.text,
                          }}
                        >
                          {loc.name}
                        </span>
                        <span
                          style={{
                            fontFamily: fonts.mono,
                            fontSize: 11,
                            color: colors.textMuted,
                          }}
                        >
                          {loc.count} incident{loc.count === 1 ? "" : "s"}
                        </span>
                      </li>
                    ))}
                  </ol>
                </section>
              )}

              {/* 05 NAMES YOU'LL SEE */}
              {entities && entities.total_mentions > 0 && (
                <section style={{ marginBottom: space.xl }}>
                  <SectionHeader
                    id="cc-names"
                    num="05"
                    stamp="NAMES YOU'LL SEE"
                    subline="people, groups, and places that come up most often in coverage"
                    count={entities.total_mentions}
                  />
                  {NAME_SUPERGROUPS.map((sg) => {
                    const items = namesBySupergroup.get(sg.key) ?? [];
                    if (items.length === 0) return null;
                    return (
                      <div key={sg.key} style={{ marginBottom: space.md }}>
                        <SubHeader
                          stamp={sg.label}
                          subline={sg.subline}
                          count={items.length}
                        />
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: `${space.xs}px ${space.sm}px`,
                          }}
                        >
                          {items.map((it) => (
                            <NameChip key={it.text} text={it.text} count={it.count} />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </section>
              )}

              {/* 06 HOW THE PIECES CONNECT */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-network"
                  num="06"
                  stamp="HOW THE PIECES CONNECT"
                  subline="groups that get mentioned together — clusters often align politically or operationally"
                />
                <RelationshipsSection slug={detail.slug} defaultOpen={true} />
              </section>

              {/* 07 SOURCES */}
              <section>
                <SectionHeader
                  id="cc-sources"
                  num="07"
                  stamp="SOURCES"
                  subline="every claim above traces back to one of these"
                  count={detail.sources.length}
                />
                <SourceList sources={detail.sources} />
              </section>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
