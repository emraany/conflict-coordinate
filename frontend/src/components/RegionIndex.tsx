import { useEffect, useMemo, useRef, useState } from "react";

import { colors, fonts, space } from "../styles/tokens";
import type { GlobeDot } from "../types";
import { violenceClassLabel } from "./dossier";

interface Props {
  dots: GlobeDot[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}

const LS_OPEN = "cc.globe.indexOpen";

/**
 * Lowercase, and normalise the dashes a keyboard cannot easily produce.
 * Region names arrive ASCII already; conflict names do not — `Israel–Hamas
 * War (Gaza)` carries an en-dash, so a typed hyphen would otherwise miss it.
 */
function fold(s: string): string {
  return s.toLowerCase().replace(/[–—]/g, "-").trim();
}

function matches(d: GlobeDot, q: string): boolean {
  return (
    // `name` is written "{admin1}, {country}", so it covers both.
    fold(d.name).includes(q) ||
    fold(d.country ?? "").includes(q) ||
    fold(d.country_iso3 ?? "").includes(q) ||
    fold(d.conflict?.name ?? "").includes(q)
  );
}

/**
 * Find a region without hunting for it on a rotating sphere. The globe holds
 * ~300 dots that collide into clusters at the default altitude; this is the
 * text way in. Selecting a row does exactly what clicking its dot does.
 */
export function RegionIndex({ dots, selectedSlug, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(
    () =>
      typeof window !== "undefined" &&
      window.localStorage.getItem(LS_OPEN) === "false",
  );
  // -1 = nothing highlighted. The list opens with no row pre-picked; a
  // tinted row on load reads as a selection the user did not make.
  const [highlight, setHighlight] = useState(-1);
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const results = useMemo(() => {
    const q = fold(query);
    // Dots arrive from /api/globe already ranked by four-week event count.
    return q === "" ? dots : dots.filter((d) => matches(d, q));
  }, [dots, query]);

  useEffect(() => {
    window.localStorage.setItem(LS_OPEN, String(!collapsed));
  }, [collapsed]);

  // A new query re-ranks the list, so the old highlight index means nothing.
  useEffect(() => setHighlight(-1), [query]);

  useEffect(() => {
    if (highlight >= 0)
      rowRefs.current[highlight]?.scrollIntoView({ block: "nearest" });
  }, [highlight]);

  if (dots.length === 0) return null;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const last = Math.max(0, results.length - 1);
      setHighlight((i) =>
        e.key === "ArrowDown" ? Math.min(i + 1, last) : Math.max(i - 1, 0),
      );
    } else if (e.key === "Enter") {
      const hit = results[highlight >= 0 ? highlight : 0];
      if (hit) onSelect(hit.slug);
    } else if (e.key === "Escape") {
      if (query) setQuery("");
      else e.currentTarget.blur();
    }
  };

  return (
    <div
      style={{
        position: "absolute",
        top: space.md,
        right: space.md,
        width: 300,
        // Clear the two-row control chip stack anchored bottom-right.
        maxHeight: "calc(100% - 140px)",
        display: "flex",
        flexDirection: "column",
        background: colors.bgRaised,
        border: `1px solid ${colors.rule}`,
        fontFamily: fonts.mono,
        zIndex: 2,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: `${space.sm}px ${space.md}px`,
          borderBottom: collapsed ? "none" : `1px solid ${colors.rule}`,
        }}
      >
        <span
          className="label"
          style={{
            fontSize: 10,
            color: colors.textMuted,
            letterSpacing: "0.18em",
          }}
        >
          [ REGION INDEX ]
        </span>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          style={{
            background: "transparent",
            border: `1px solid ${colors.rule}`,
            color: colors.textMuted,
            fontFamily: fonts.mono,
            fontSize: 10,
            lineHeight: 1,
            padding: "3px 8px",
            cursor: "pointer",
          }}
          title={collapsed ? "Show the region list" : "Hide the region list"}
        >
          {collapsed ? "+" : "–"}
        </button>
      </div>

      {!collapsed && (
        <>
          <div
            style={{
              padding: `${space.sm}px ${space.md}px`,
              borderBottom: `1px solid ${colors.rule}`,
            }}
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="region, country or conflict..."
              style={{
                background: colors.bgSunken,
                border: `1px solid ${colors.rule}`,
                color: colors.text,
                fontFamily: fonts.mono,
                fontSize: 11,
                padding: "4px 10px",
                outline: "none",
                width: "100%",
                boxSizing: "border-box",
              }}
            />
            <div
              style={{
                fontSize: 9,
                color: colors.textDim,
                letterSpacing: "0.12em",
                marginTop: 4,
              }}
            >
              {query
                ? `${results.length} OF ${dots.length}`
                : `${dots.length} REGIONS`}{" "}
              · ↑↓ ENTER
            </div>
          </div>

          <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
            {results.length === 0 ? (
              <div
                style={{
                  padding: space.md,
                  fontSize: 10,
                  color: colors.textDim,
                  letterSpacing: "0.1em",
                }}
              >
                {"// NO REGION MATCHES"}
              </div>
            ) : (
              results.map((d, i) => {
                const isSelected = d.slug === selectedSlug;
                const classed =
                  d.violence_class && d.violence_class !== "unclear";
                return (
                  <button
                    key={d.slug}
                    ref={(el) => {
                      rowRefs.current[i] = el;
                    }}
                    type="button"
                    onClick={() => onSelect(d.slug)}
                    onMouseEnter={() => setHighlight(i)}
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      background: isSelected
                        ? `color-mix(in srgb, ${colors.oliveLight} 14%, transparent)`
                        : i === highlight
                          ? `color-mix(in srgb, ${colors.oliveLight} 8%, transparent)`
                          : "transparent",
                      border: "none",
                      borderLeft: `2px solid ${isSelected ? colors.oliveLight : "transparent"}`,
                      color: colors.text,
                      fontFamily: fonts.mono,
                      padding: `6px ${space.md}px`,
                      cursor: "pointer",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: space.sm,
                        alignItems: "baseline",
                      }}
                    >
                      <span
                        style={{
                          fontSize: 9,
                          color: colors.textDim,
                          minWidth: 26,
                        }}
                      >
                        [{String(i + 1).padStart(2, "0")}]
                      </span>
                      <span style={{ fontSize: 11 }}>{d.name}</span>
                    </div>
                    <div
                      style={{
                        fontSize: 9,
                        color: colors.textMuted,
                        letterSpacing: "0.03em",
                        marginTop: 2,
                        paddingLeft: 34,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {d.events_4w.toLocaleString()} events
                      {d.fatalities_4w > 0
                        ? ` · † ${d.fatalities_4w.toLocaleString()}`
                        : ""}{" "}
                      ·{" "}
                      <span
                        style={{
                          color: classed ? colors.oliveLight : colors.textDim,
                        }}
                      >
                        {violenceClassLabel(d.violence_class)}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}
