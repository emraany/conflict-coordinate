import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Brief } from "../components/Brief";
import {
  Globe,
  LS_CLASSFILTER,
  lethalityColor,
  readLocal,
} from "../components/Globe";
import type { ClassFilter } from "../components/Globe";
import { RegionDetailPanel } from "../components/RegionDetailPanel";
import { RegionIndex } from "../components/RegionIndex";
import { colors, fonts, space } from "../styles/tokens";
import type { GlobeDot, ViolenceClass } from "../types";
import { VIOLENCE_CLASS_LABEL } from "../components/dossier";

const CLASS_ORDER: ViolenceClass[] = [
  "armed_conflict",
  "criminal_violence",
  "unrest",
  "unclear",
];

function Legend({
  latestWeek,
  dots,
}: {
  latestWeek: string | null;
  dots: GlobeDot[];
}) {
  const byClass = CLASS_ORDER.map((c) => ({
    cls: c,
    n: dots.filter((d) => (d.violence_class ?? "unclear") === c).length,
  })).filter((row) => row.n > 0);
  // Ramp samples match lethalityColor(fatalities) in Globe.tsx.
  const ramp = [0, 5, 25, 120, 600];
  return (
    <div
      style={{
        position: "absolute",
        left: space.md,
        bottom: space.md,
        background: colors.bgRaised,
        border: `1px solid ${colors.rule}`,
        padding: `${space.sm}px ${space.md}px`,
        fontFamily: fonts.mono,
        fontSize: 11,
        maxWidth: 300,
      }}
    >
      <div
        className="label"
        style={{ fontSize: 10, color: colors.textMuted, marginBottom: 6 }}
      >
        REPORTED DEATHS · 4 WEEKS
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
        {ramp.map((f) => (
          <span
            key={f}
            style={{
              width: 26,
              height: 10,
              background: lethalityColor(f),
              display: "inline-block",
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          color: colors.textDim,
          fontSize: 9,
          letterSpacing: "0.1em",
          marginTop: 3,
        }}
      >
        <span>NONE</span>
        <span>MANY</span>
      </div>
      <div
        style={{
          fontSize: 9,
          color: colors.textDim,
          lineHeight: 1.5,
          marginTop: 6,
          letterSpacing: "0.04em",
        }}
      >
        Dot size = recorded events. Each dot is one admin1 region with armed
        violence or riots in the four weeks to{" "}
        <span style={{ color: colors.textMuted }}>{latestWeek ?? "—"}</span>,
        per ACLED weekly aggregates (published ~1–2 weeks behind).
      </div>
      <div
        className="label"
        style={{
          fontSize: 10,
          color: colors.textMuted,
          marginTop: space.sm,
          paddingTop: space.sm,
          borderTop: `1px solid ${colors.rule}`,
        }}
      >
        BY KIND OF VIOLENCE
      </div>
      <div
        style={{
          fontSize: 9,
          color: colors.textDim,
          lineHeight: 1.6,
          letterSpacing: "0.04em",
        }}
      >
        {byClass.map((row, i) => (
          <span key={row.cls}>
            {i > 0 ? " · " : ""}
            {VIOLENCE_CLASS_LABEL[row.cls].toLowerCase()}{" "}
            <span style={{ color: colors.textMuted }}>{row.n}</span>
          </span>
        ))}
        <br />
        Classed from each region's own actors and event mix; filter with the
        chips at bottom right.
      </div>
    </div>
  );
}

export function MapPage() {
  const [dots, setDots] = useState<GlobeDot[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Owned here, not in Globe, so the region index and the globe filter the
  // same set.
  const [classFilter, setClassFilter] = useState<ClassFilter>(() =>
    readLocal<ClassFilter>(LS_CLASSFILTER, "all"),
  );

  useEffect(() => {
    api
      .listGlobeDots()
      .then(setDots)
      .catch(() => setError("Unable to reach API"));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(LS_CLASSFILTER, classFilter);
  }, [classFilter]);

  // The index searches every region, so a hit can be one the class filter is
  // currently hiding. Clear the filter rather than fly the camera to a dot
  // that will not be drawn. A globe click can never trip this — a dot you can
  // click already passes the filter.
  const handleSelect = (slug: string) => {
    setSelectedSlug(slug);
    const dot = dots.find((d) => d.slug === slug);
    if (dot && classFilter !== "all" && dot.violence_class !== classFilter) {
      setClassFilter("all");
    }
  };

  const namedCount = dots.filter((d) => d.conflict !== null).length;
  const latestWeek = dots.reduce<string | null>(
    (max, d) =>
      d.latest_week && (max === null || d.latest_week > max) ? d.latest_week : max,
    null,
  );

  return (
    <Brief
      section="globe"
      rightMeta={
        <>
          <span style={{ color: colors.active }}>
            {dots.length} active regions
          </span>
          <span style={{ color: colors.textMuted }}>
            {namedCount} in named conflicts
          </span>
          <span style={{ color: colors.textMuted }}>
            week of {latestWeek ?? "—"}
          </span>
          <a
            href="/admin"
            style={{ color: colors.textMuted, textDecoration: "none" }}
          >
            /admin
          </a>
        </>
      }
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "row",
        }}
      >
        <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
          <Globe
            dots={dots}
            onSelect={handleSelect}
            selectedSlug={selectedSlug}
            classFilter={classFilter}
            onSetClassFilter={setClassFilter}
          />
          <Legend latestWeek={latestWeek} dots={dots} />
          <RegionIndex
            dots={dots}
            selectedSlug={selectedSlug}
            onSelect={handleSelect}
          />
          {error && (
            <div
              style={{
                position: "absolute",
                top: space.md,
                left: "50%",
                transform: "translateX(-50%)",
                background: colors.bgRaised,
                border: `1px solid ${colors.active}`,
                padding: `${space.sm}px ${space.md}px`,
                color: colors.active,
              }}
            >
              <span className="stamp">CONNECTION FAILURE</span> — {error}
            </div>
          )}
        </div>
        {selectedSlug && (
          <div
            style={{
              width: "min(1200px, 66vw)",
              flexShrink: 0,
              borderLeft: `1px solid ${colors.ruleStrong}`,
              background: colors.bgRaised,
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <RegionDetailPanel
              slug={selectedSlug}
              onClose={() => setSelectedSlug(null)}
            />
          </div>
        )}
      </div>
    </Brief>
  );
}
