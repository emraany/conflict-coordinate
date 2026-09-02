import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { colors, fonts, space } from "../styles/tokens";
import type {
  ActorRole,
  ConflictDetail,
  ConflictParty,
  CrisisEvent,
  TopAdmin1,
} from "../types";
import { ActorList } from "./ActorList";
import {
  EventTypeBreakdown,
  FieldReportList,
  IntensitySparkline,
  SectionHeader,
  StatTile,
  SubHeader,
  activityFromWeeks,
  formatDuration,
  formatMonth,
  formatYmd,
} from "./dossier";
import { EventTimeline } from "./EventTimeline";
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

const SECTION_NAV: Array<{ id: string; num: string; label: string }> = [
  { id: "cc-glance", num: "01", label: "GLANCE" },
  { id: "cc-reports", num: "02", label: "REPORTS" },
  { id: "cc-who", num: "03", label: "WHO" },
  { id: "cc-when", num: "04", label: "TIMELINE" },
  { id: "cc-where", num: "05", label: "WHERE" },
  { id: "cc-sources", num: "06", label: "SOURCES" },
];

function CountryLine({
  primary,
  secondary,
}: {
  primary: string | null;
  secondary: string[];
}) {
  if (!primary && secondary.length === 0) return <span>—</span>;
  return (
    <>
      <span style={{ color: colors.text }}>{primary ?? "—"}</span>
      {secondary.length > 0 && (
        <>
          <span style={{ color: colors.textDim }}> · with </span>
          <span style={{ color: colors.text }}>{secondary.join(", ")}</span>
        </>
      )}
    </>
  );
}

function TopAdmin1List({ rows }: { rows: TopAdmin1[] }) {
  if (rows.length === 0) {
    return (
      <div className="label" style={{ color: colors.textDim }}>
        (no event-level admin1 records yet)
      </div>
    );
  }
  return (
    <ol style={{ margin: 0, padding: 0, listStyle: "none" }}>
      {rows.map((r, i) => (
        <li
          key={`${r.iso3}-${r.admin1}`}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: space.md,
            paddingTop: space.xs,
            paddingBottom: space.xs,
            borderBottom:
              i === rows.length - 1
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
            {r.admin1}
            <span style={{ color: colors.textDim }}> · {r.iso3}</span>
          </span>
          <span
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              color: colors.textMuted,
            }}
          >
            {r.event_count} event{r.event_count === 1 ? "" : "s"}
          </span>
        </li>
      ))}
    </ol>
  );
}

export function ConflictDetailPanel({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<ConflictDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAllParties, setShowAllParties] = useState(false);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setShowAllParties(false);
    setShowAllTimeline(false);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getConflict(slug)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(e.status === 404 ? "Not found" : `Error ${e.status}`);
        } else {
          setError("Error loading conflict");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
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

  const partiesByRole = useMemo(() => {
    const map = new Map<ActorRole, ConflictParty[]>();
    if (!detail) return map;
    for (const link of detail.parties) {
      const arr = map.get(link.role) ?? [];
      arr.push(link);
      map.set(link.role, arr);
    }
    return map;
  }, [detail]);

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
              <CountryLine
                primary={detail.primary_iso3}
                secondary={detail.secondary_iso3s}
              />
              {detail.conflict_type && (
                <>
                  <span style={{ color: colors.textDim }}>·</span>
                  <span>{detail.conflict_type}</span>
                </>
              )}
              <span style={{ color: colors.textDim }}>·</span>
              <span>
                {detail.status === "active"
                  ? `active — last recorded activity ${formatYmd(detail.last_event_at)}`
                  : detail.status === "frozen"
                    ? `dormant — last activity ${formatMonth(detail.last_event_at)}`
                    : detail.status === "emerging"
                      ? "emerging — auto-discovered, unconfirmed"
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
                  subline="the conflict in a few numbers and a paragraph"
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
                  <StatTile
                    label="TOTAL INCIDENTS ON FILE"
                    value={detail.stats.total_events.toLocaleString()}
                  />
                </div>
                {detail.stats.gdelt_7d_reports > 0 && (
                  <div
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 11,
                      color: colors.oliveLight,
                      letterSpacing: "0.06em",
                      marginBottom: space.md,
                    }}
                    title="Machine-coded event reports from the GDELT stream — a freshness signal, not verified incident records"
                  >
                    ▸ {detail.stats.gdelt_7d_reports.toLocaleString()} violent-event
                    report{detail.stats.gdelt_7d_reports === 1 ? "" : "s"} in the
                    last 7 days
                    <span style={{ color: colors.textDim }}> · GDELT signal</span>
                  </div>
                )}
                {detail.intensity_52w.length > 0 && (
                  <>
                    <IntensitySparkline
                      weeks={detail.intensity_52w}
                      caption="WEEKLY EVENT COUNT — ALL ROUTED SOURCES"
                    />
                    <EventTypeBreakdown activity={activityFromWeeks(detail.intensity_52w)} />
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
                {detail.wikipedia_url && (
                  <div style={{ marginTop: space.sm }}>
                    <a
                      href={detail.wikipedia_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontFamily: fonts.mono,
                        fontSize: 11,
                        color: colors.oliveLight,
                        letterSpacing: "0.16em",
                        border: `1px solid ${colors.oliveDim}`,
                        padding: `${space.xs}px ${space.sm}px`,
                        textDecoration: "none",
                      }}
                    >
                      [ READ ON WIKIPEDIA ]
                    </a>
                  </div>
                )}
              </section>

              {/* 02 LATEST REPORTING */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-reports"
                  num="02"
                  stamp="LATEST REPORTING"
                  subline="recent situation reports from humanitarian agencies on the ground"
                  count={detail.field_reports.length}
                />
                <FieldReportList reports={detail.field_reports} />
              </section>

              {/* 03 WHO IS INVOLVED */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-who"
                  num="03"
                  stamp="WHO IS INVOLVED"
                  subline="the sides of the conflict, who is mediating, and who is caught in the middle"
                  count={detail.parties.length}
                />
                {detail.parties.length === 0 ? (
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
                    No curated parties on file yet for this conflict.
                  </p>
                ) : (
                  <>
                    {ROLE_GROUPS.map((rg) => {
                      const actors = partiesByRole.get(rg.role) ?? [];
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
                    {detail.parties.length > 5 && (
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
                          : `[ show all ${detail.parties.length} ]`}
                      </button>
                    )}
                  </>
                )}
              </section>

              {/* 04 HOW IT'S UNFOLDING */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-when"
                  num="04"
                  stamp="HOW IT'S UNFOLDING"
                  subline="individual incidents routed to this conflict — sourced from ACLED and UCDP; near-real-time GDELT activity appears as the signal count above"
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
                    no individual incident records are attached yet. Detailed
                    events populate as the ACLED API window advances and
                    UCDP/GDELT feeds match this footprint.
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
                          events={visible as CrisisEvent[]}
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

              {/* 05 WHERE IT'S HAPPENING */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="cc-where"
                  num="05"
                  stamp="WHERE IT'S HAPPENING"
                  subline="the admin1 regions seeing the most activity"
                  count={detail.top_admin1s.length}
                />
                <TopAdmin1List rows={detail.top_admin1s} />
              </section>

              {/* 06 SOURCES */}
              <section>
                <SectionHeader
                  id="cc-sources"
                  num="06"
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
