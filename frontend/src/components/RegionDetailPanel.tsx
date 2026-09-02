import { useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { colors, fonts, space } from "../styles/tokens";
import type { ActorRole, CrisisDetail } from "../types";
import { ActorList } from "./ActorList";
import { EventTimeline } from "./EventTimeline";
import { SourceList } from "./SourceList";
import {
  EventTypeBreakdown,
  FieldReportList,
  IntensitySparkline,
  SectionHeader,
  StatTile,
  SubHeader,
  activitySummary,
  formatYmd,
  violenceClassLabel,
} from "./dossier";

interface Props {
  slug: string | null;
  onClose: () => void;
}

const ROLE_GROUPS: Array<{ role: ActorRole; label: string; subline: string }> = [
  { role: "party", label: "PARTIES", subline: "actively engaged in the conflict" },
  {
    role: "mediator",
    label: "MEDIATORS",
    subline: "external parties working toward resolution",
  },
  { role: "observer", label: "OBSERVERS", subline: "monitoring without taking sides" },
  {
    role: "affected",
    label: "AFFECTED",
    subline: "civilian populations bearing the brunt",
  },
];

const SECTION_NAV: Array<{ id: string; num: string; label: string }> = [
  { id: "rr-now", num: "01", label: "NOW" },
  { id: "rr-reports", num: "02", label: "REPORTS" },
  { id: "rr-who", num: "03", label: "WHO" },
  { id: "rr-archive", num: "04", label: "ARCHIVE" },
  { id: "rr-sources", num: "05", label: "SOURCES" },
];

/**
 * The dossier for one globe dot: an admin1 region.
 *
 * Two clearly separated layers, because their currency differs by months:
 * section 01 is ACLED's real-time weekly aggregate (what is happening now),
 * section 04 is the incident archive (ACLED's event API is embargoed ~12
 * months; UCDP lands a month or two behind). Labels say so plainly rather
 * than letting a reader assume the incident list is current.
 */
export function RegionDetailPanel({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<CrisisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setShowAllTimeline(false);
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
          setError("Error loading region");
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
    const map = new Map<ActorRole, CrisisDetail["actors"]>();
    const parties = detail?.conflict_context?.parties ?? [];
    for (const link of parties) {
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

  const ctx = detail?.conflict_context ?? null;

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
          {/* What is happening leads; where it is happening follows. */}
          <div
            style={{
              fontFamily: fonts.stamp,
              fontSize: 22,
              letterSpacing: "0.04em",
              color: colors.text,
              lineHeight: 1.15,
            }}
          >
            {detail
              ? (activitySummary(detail.activity) ?? "Recorded violence")
              : loading
                ? "LOADING…"
                : slug}
          </div>
          {detail && (
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 14,
                color: colors.textMuted,
                letterSpacing: "0.06em",
                marginTop: 3,
              }}
            >
              {detail.name}
            </div>
          )}
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
              {/* What kind of violence, before which conflict claims it — the
                  class is derived from this region's own evidence, the name
                  from the registry. `title` carries that evidence. */}
              <span
                style={{
                  color:
                    detail.violence_class && detail.violence_class !== "unclear"
                      ? colors.text
                      : colors.textDim,
                  border: `1px solid ${colors.rule}`,
                  padding: "1px 6px",
                  fontSize: 10,
                  letterSpacing: "0.14em",
                }}
                title={detail.violence_class_basis ?? undefined}
              >
                {violenceClassLabel(detail.violence_class)}
              </span>
              {ctx ? (
                <span
                  style={{
                    color: colors.oliveLight,
                    border: `1px solid ${colors.oliveDim}`,
                    padding: "1px 6px",
                    fontSize: 10,
                    letterSpacing: "0.14em",
                  }}
                >
                  {ctx.name.toUpperCase()}
                </span>
              ) : (
                <span
                  style={{
                    color: colors.textDim,
                    border: `1px solid ${colors.rule}`,
                    padding: "1px 6px",
                    fontSize: 10,
                    letterSpacing: "0.14em",
                  }}
                  title="No named conflict in the registry claims this region"
                >
                  NO NAMED CONFLICT
                </span>
              )}
              <span>
                {detail.violence_4w_events.toLocaleString()} events
                {detail.violence_4w_fatalities > 0
                  ? ` · † ${detail.violence_4w_fatalities.toLocaleString()} killed`
                  : " · no deaths reported"}
              </span>
              <span style={{ color: colors.textDim }}>·</span>
              <span>4 weeks to {detail.latest_agg_week ?? "—"}</span>
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
              {/* 01 RIGHT NOW */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="rr-now"
                  num="01"
                  stamp="RIGHT NOW"
                  subline="recorded activity in the last four weeks, from ACLED's weekly aggregates"
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
                    label="EVENTS · 4 WEEKS"
                    value={detail.violence_4w_events.toLocaleString()}
                    hint={`to ${detail.latest_agg_week ?? "—"}`}
                  />
                  <StatTile
                    label="REPORTED DEATHS · 4 WEEKS"
                    value={detail.violence_4w_fatalities.toLocaleString()}
                  />
                  <StatTile
                    label="PEOPLE IN AFFECTED AREA"
                    value={
                      detail.violence_4w_pop_exposure
                        ? detail.violence_4w_pop_exposure.toLocaleString()
                        : "—"
                    }
                    hint="admin1 population"
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
                    title="Machine-coded news reports from the GDELT stream — a freshness signal, not verified incident records"
                  >
                    ▸ {detail.stats.gdelt_7d_reports.toLocaleString()} news report
                    {detail.stats.gdelt_7d_reports === 1 ? "" : "s"} in the last 7
                    days
                    <span style={{ color: colors.textDim }}> · GDELT signal</span>
                  </div>
                )}
                {detail.intensity_52w.length > 0 && (
                  <>
                    <IntensitySparkline
                      weeks={detail.intensity_52w}
                      caption="WEEKLY EVENT COUNT — ACLED AGGREGATES"
                    />
                    <EventTypeBreakdown activity={detail.activity} />
                  </>
                )}
              </section>

              {/* 02 LATEST REPORTING */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="rr-reports"
                  num="02"
                  stamp="LATEST REPORTING"
                  subline="recent situation reports from humanitarian agencies covering this country"
                  count={detail.field_reports.length}
                />
                <FieldReportList reports={detail.field_reports} />
              </section>

              {/* 03 WHO IS INVOLVED */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="rr-who"
                  num="03"
                  stamp="WHO IS INVOLVED"
                  subline={
                    ctx
                      ? `curated parties to ${ctx.name}`
                      : "no named conflict claims this region"
                  }
                  count={ctx ? ctx.parties.length : undefined}
                />
                {ctx ? (
                  <>
                    {ctx.summary && (
                      <p
                        className="serif"
                        style={{
                          margin: `0 0 ${space.md}px 0`,
                          fontSize: 14,
                          lineHeight: 1.7,
                          color: colors.text,
                        }}
                      >
                        {ctx.summary}
                      </p>
                    )}
                    {ROLE_GROUPS.map((rg) => {
                      const actors = partiesByRole.get(rg.role) ?? [];
                      if (actors.length === 0) return null;
                      return (
                        <div key={rg.role} style={{ marginBottom: space.md }}>
                          <SubHeader
                            stamp={rg.label}
                            subline={rg.subline}
                            count={actors.length}
                          />
                          <ActorList actors={actors} sourceIndex={sourceIndex} />
                        </div>
                      );
                    })}
                  </>
                ) : (
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
                    Violence recorded here is not attributed to a named conflict in
                    the registry. The incidents below name the actors involved as
                    their sources reported them.
                  </p>
                )}
              </section>

              {/* 04 INCIDENT ARCHIVE */}
              <section style={{ marginBottom: space.xl }}>
                <SectionHeader
                  id="rr-archive"
                  num="04"
                  stamp="INCIDENT ARCHIVE"
                  subline="individual incidents with published descriptions — these lag the counts above, since ACLED embargoes event-level records for ~12 months and UCDP publishes a month or two behind"
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
                    Activity here is recorded in the weekly counts above, but no
                    individual incident records have been published for this region
                    yet.
                  </p>
                ) : (
                  (() => {
                    const LIMIT = 10;
                    const visible = showAllTimeline
                      ? detail.events
                      : detail.events.slice(0, LIMIT);
                    const hidden = detail.events.length - visible.length;
                    const newest = detail.events[0]?.occurred_at ?? null;
                    return (
                      <>
                        <div
                          className="label"
                          style={{
                            fontSize: 10,
                            color: colors.textDim,
                            marginBottom: space.sm,
                          }}
                        >
                          MOST RECENT PUBLISHED INCIDENT — {formatYmd(newest)}
                        </div>
                        <EventTimeline events={visible} sourceIndex={sourceIndex} />
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

              {/* 05 SOURCES */}
              <section>
                <SectionHeader
                  id="rr-sources"
                  num="05"
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
