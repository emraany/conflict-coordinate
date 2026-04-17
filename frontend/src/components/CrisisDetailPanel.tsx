import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import { fetchCountryInfo, formatPopulation } from "../api/countryInfo";
import type { CountryInfo } from "../api/countryInfo";
import { colors, fonts, space } from "../styles/tokens";
import type { CrisisDetail } from "../types";
import { ActorList } from "./ActorList";
import { EventTimeline } from "./EventTimeline";
import { SourceList } from "./SourceList";
import { StatusChip } from "./StatusChip";

interface Props {
  slug: string | null;
  onClose: () => void;
}

function formatStartDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toISOString().slice(0, 10);
}

function SectionHeader({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        marginBottom: space.sm,
        paddingBottom: space.xs,
        borderBottom: `1px solid ${colors.rule}`,
      }}
    >
      <span
        className="stamp"
        style={{ fontSize: 11, color: colors.oliveLight, letterSpacing: "0.22em" }}
      >
        {children}
      </span>
      {typeof count === "number" && (
        <span
          className="label"
          style={{ fontSize: 10, color: colors.textMuted }}
        >
          [{String(count).padStart(2, "0")}]
        </span>
      )}
    </div>
  );
}

export function CrisisDetailPanel({ slug, onClose }: Props) {
  const [detail, setDetail] = useState<CrisisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [countryInfo, setCountryInfo] = useState<CountryInfo | null>(null);

  useEffect(() => {
    if (!detail?.country) { setCountryInfo(null); return; }
    fetchCountryInfo(detail.country).then(setCountryInfo);
  }, [detail?.country]);

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

  if (!slug) return null;

  return (
    <aside
      style={{
        position: "absolute",
        top: space.md,
        right: space.md,
        bottom: space.md,
        width: 460,
        maxWidth: "calc(100vw - 48px)",
        background: colors.bgRaised,
        border: `1px solid ${colors.ruleStrong}`,
        display: "flex",
        flexDirection: "column",
        boxShadow: `0 20px 40px ${colors.inkShadow}`,
        animation: "cc-fade-in 180ms cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <style>{`
        @keyframes cc-fade-in {
          from { opacity: 0; transform: translateX(8px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
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
            className="label"
            style={{ color: colors.textMuted, fontSize: 10 }}
          >
            DOSSIER // {detail?.slug ?? slug}
          </div>
          <div
            style={{
              marginTop: 4,
              fontFamily: fonts.stamp,
              fontSize: 18,
              letterSpacing: "0.08em",
              color: colors.text,
              lineHeight: 1.25,
            }}
          >
            {detail?.name ?? (loading ? "LOADING…" : slug)}
          </div>
        </div>
        <button onClick={onClose} style={{ fontSize: 10 }}>
          Close
        </button>
      </div>

      <div
        style={{
          padding: `${space.md}px ${space.lg}px`,
          overflowY: "auto",
          flex: 1,
        }}
      >
        {error && (
          <div style={{ color: colors.active }}>
            <span className="stamp">ERROR</span> — {error}
          </div>
        )}
        {detail && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr",
                columnGap: space.md,
                rowGap: space.xs,
                marginBottom: space.lg,
                fontSize: 12,
              }}
            >
              <span className="label">Status</span>
              <span>
                <StatusChip status={detail.status} />
              </span>
              <span className="label">Country</span>
              <span>{detail.country ?? "—"}</span>
              <span className="label">Region</span>
              <span>{detail.region ?? "—"}</span>
              <span className="label">Type</span>
              <span style={{ color: colors.text }}>
                {detail.conflict_type ?? "—"}
              </span>
              <span className="label">Onset</span>
              <span>{formatStartDate(detail.started_at)}</span>
              <span className="label">Last event</span>
              <span>{formatStartDate(detail.last_event_at)}</span>
              <span className="label">Coordinates</span>
              <span>
                {detail.lat.toFixed(3)}, {detail.lng.toFixed(3)}
              </span>
              {countryInfo && countryInfo.capital && (
                <>
                  <span className="label">Capital</span>
                  <span>{countryInfo.capital}</span>
                </>
              )}
              {countryInfo && countryInfo.population > 0 && (
                <>
                  <span className="label">Population</span>
                  <span>{formatPopulation(countryInfo.population)}</span>
                </>
              )}
              {countryInfo && countryInfo.language && (
                <>
                  <span className="label">Language</span>
                  <span>{countryInfo.language}</span>
                </>
              )}
              {countryInfo && countryInfo.borders.length > 0 && (
                <>
                  <span className="label">Borders</span>
                  <span
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 11,
                      letterSpacing: "0.08em",
                      color: colors.textMuted,
                    }}
                  >
                    {countryInfo.borders.join(" · ")}
                  </span>
                </>
              )}
            </div>

            {detail.stats.total_events > 0 && (
              <div
                style={{
                  marginBottom: space.lg,
                  padding: `${space.sm}px ${space.md}px`,
                  background: colors.bgSunken,
                  border: `1px solid ${colors.rule}`,
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  color: colors.textMuted,
                  display: "flex",
                  flexWrap: "wrap",
                  gap: `${space.xs}px ${space.lg}px`,
                  lineHeight: 1.6,
                }}
              >
                <span>
                  <span style={{ color: colors.text }}>{detail.stats.total_events}</span>
                  {" "}incidents
                </span>
                {detail.stats.total_fatalities > 0 && (
                  <span>
                    <span style={{ color: colors.active }}>†</span>
                    {" "}
                    <span style={{ color: colors.text }}>{detail.stats.total_fatalities.toLocaleString()}</span>
                    {" "}fatalities
                  </span>
                )}
                {Object.entries(detail.stats.event_type_counts)
                  .slice(0, 3)
                  .map(([type, count]) => (
                    <span key={type}>
                      <span style={{ color: colors.oliveLight }}>{type}</span>
                      {" "}
                      <span style={{ color: colors.textDim }}>[{count}]</span>
                    </span>
                  ))}
              </div>
            )}

            {detail.summary && (
              <section style={{ marginBottom: space.lg }}>
                <SectionHeader>SITUATION</SectionHeader>
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
              </section>
            )}

            {(() => {
              const backgrounds = detail.sources.filter(
                (s) => s.source_type === "reference" && s.body_text,
              );
              if (backgrounds.length === 0) return null;
              const bg = backgrounds[0];
              return (
                <section style={{ marginBottom: space.lg }}>
                  <SectionHeader>BACKGROUND</SectionHeader>
                  <p
                    className="serif"
                    style={{
                      margin: 0,
                      fontSize: 13,
                      lineHeight: 1.7,
                      color: colors.text,
                    }}
                  >
                    {bg.body_text}
                  </p>
                  <div
                    className="label"
                    style={{
                      marginTop: space.xs,
                      fontSize: 10,
                      color: colors.textMuted,
                    }}
                  >
                    Source:{" "}
                    <a
                      href={bg.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: colors.oliveLight }}
                    >
                      {bg.title}
                    </a>
                    {bg.publisher && ` · ${bg.publisher}`}
                  </div>
                </section>
              );
            })()}

            <section style={{ marginBottom: space.lg }}>
              <SectionHeader count={detail.actors.length}>
                PARTIES INVOLVED
              </SectionHeader>
              <ActorList actors={detail.actors} sources={detail.sources} />
            </section>

            {(() => {
              const sitreps = detail.sources.filter(
                (s) => s.source_type === "situation_report" && s.body_text,
              );
              if (sitreps.length === 0) return null;
              return (
                <section style={{ marginBottom: space.lg }}>
                  <SectionHeader count={sitreps.length}>FIELD REPORTS</SectionHeader>
                  {sitreps.map((s) => (
                    <div
                      key={s.id}
                      style={{
                        marginBottom: space.md,
                        paddingBottom: space.sm,
                        borderBottom: `1px dashed ${colors.rule}`,
                      }}
                    >
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="label"
                        style={{
                          color: colors.oliveLight,
                          fontSize: 10,
                          letterSpacing: "0.14em",
                          wordBreak: "break-word",
                        }}
                      >
                        {s.title}
                      </a>
                      <p
                        className="serif"
                        style={{
                          margin: `${space.xs}px 0 0 0`,
                          fontSize: 13,
                          lineHeight: 1.6,
                          color: colors.text,
                        }}
                      >
                        {s.body_text}
                      </p>
                      {s.publisher && (
                        <div
                          className="label"
                          style={{
                            marginTop: space.xs,
                            fontSize: 10,
                            color: colors.textMuted,
                          }}
                        >
                          {s.publisher}
                        </div>
                      )}
                    </div>
                  ))}
                </section>
              );
            })()}

            {detail.events.length > 0 && (
              <section style={{ marginBottom: space.lg }}>
                <SectionHeader count={detail.events.length}>TIMELINE</SectionHeader>
                <EventTimeline events={detail.events} sources={detail.sources} />
              </section>
            )}

            {(() => {
              const citedSources = detail.sources.filter(
                (s) =>
                  s.source_type !== "reference" &&
                  s.source_type !== "situation_report",
              );
              return (
                <section style={{ marginBottom: space.lg }}>
                  <SectionHeader count={citedSources.length}>SOURCES</SectionHeader>
                  <SourceList sources={citedSources} />
                </section>
              );
            })()}

            <div
              className="label"
              style={{
                marginTop: space.lg,
                paddingTop: space.sm,
                borderTop: `1px solid ${colors.rule}`,
                fontSize: 10,
                color: colors.textDim,
                lineHeight: 1.5,
              }}
            >
              ALL INFORMATION IS ATTRIBUTED TO LINKED SOURCES. NO EDITORIAL
              INTERPRETATION.
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
