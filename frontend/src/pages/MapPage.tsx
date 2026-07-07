import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Brief } from "../components/Brief";
import { ConflictDetailPanel } from "../components/ConflictDetailPanel";
import { Globe } from "../components/Globe";
import { colors, fonts, space, statusColor } from "../styles/tokens";
import type { ConflictListItem, ConflictStatus } from "../types";

function Legend() {
  const rows: { label: string; status: ConflictStatus }[] = [
    { label: "ACTIVE", status: "active" },
    { label: "FROZEN", status: "frozen" },
    { label: "EMERGING", status: "emerging" },
  ];
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
      }}
    >
      <div
        className="label"
        style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4 }}
      >
        LEGEND
      </div>
      {rows.map((r) => (
        <div
          key={r.status}
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.sm,
            padding: "2px 0",
          }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              background: statusColor(r.status),
              display: "inline-block",
              borderRadius: "50%",
            }}
          />
          <span style={{ color: colors.textMuted, letterSpacing: "0.12em" }}>
            {r.label}
          </span>
        </div>
      ))}
    </div>
  );
}

export function MapPage() {
  const [conflicts, setConflicts] = useState<ConflictListItem[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listConflicts()
      .then(setConflicts)
      .catch(() => setError("Unable to reach API"));
  }, []);

  const activeCount = conflicts.filter((c) => c.status === "active").length;

  return (
    <Brief
      section="globe"
      rightMeta={
        <>
          <span style={{ color: colors.textMuted }}>
            {conflicts.length} conflicts
          </span>
          <span style={{ color: colors.active }}>{activeCount} active</span>
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
            conflicts={conflicts}
            onSelect={setSelectedSlug}
            selectedSlug={selectedSlug}
          />
          <Legend />
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
            <ConflictDetailPanel
              slug={selectedSlug}
              onClose={() => setSelectedSlug(null)}
            />
          </div>
        )}
      </div>
    </Brief>
  );
}
