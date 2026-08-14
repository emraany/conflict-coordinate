import type { ReactNode } from "react";
import { Brief } from "../components/Brief";
import { colors, fonts, space } from "../styles/tokens";

function Section({ num, title, children }: { num: string; title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: space.xl }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: space.sm,
          borderBottom: `1px solid ${colors.rule}`,
          paddingBottom: space.xs,
          marginBottom: space.md,
        }}
      >
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 10,
            color: colors.textDim,
            letterSpacing: "0.16em",
          }}
        >
          [{num}]
        </span>
        <span
          className="stamp"
          style={{ fontSize: 12, letterSpacing: "0.22em", color: colors.text }}
        >
          {title}
        </span>
      </div>
      <div
        style={{
          fontFamily: fonts.serif,
          fontSize: 14,
          lineHeight: 1.75,
          color: colors.text,
        }}
      >
        {children}
      </div>
    </section>
  );
}

function SourceRow({
  name,
  role,
  url,
  note,
}: {
  name: string;
  role: string;
  url: string;
  note: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "160px 120px 1fr",
        gap: space.md,
        padding: `${space.sm}px 0`,
        borderBottom: `1px solid rgba(82,88,98,0.4)`,
        fontFamily: fonts.mono,
        fontSize: 12,
        alignItems: "baseline",
      }}
    >
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        style={{ color: colors.oliveLight, textDecoration: "none", letterSpacing: "0.06em" }}
      >
        {name}
      </a>
      <span style={{ color: colors.textMuted, fontSize: 10, letterSpacing: "0.18em" }}>
        {role}
      </span>
      <span style={{ color: colors.textDim, fontSize: 12, lineHeight: 1.6 }}>
        {note}
      </span>
    </div>
  );
}

function Rule({ children }: { children: ReactNode }) {
  return (
    <li style={{ marginBottom: space.sm, paddingLeft: space.sm }}>
      {children}
    </li>
  );
}

export function AboutPage() {
  return (
    <Brief
      section="about"
      rightMeta={
        <>
          <a href="/admin" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /admin
          </a>
        </>
      }
    >
      <div
        style={{
          height: "100%",
          overflowY: "auto",
          padding: `${space.lg}px ${space.xl}px`,
        }}
      >
        <div style={{ maxWidth: 820, margin: "0 auto" }}>
          {/* Document header */}
          <div
            style={{
              textAlign: "center",
              borderTop: `2px solid ${colors.rule}`,
              borderBottom: `2px solid ${colors.rule}`,
              padding: `${space.md}px 0`,
              marginBottom: space.xl,
            }}
          >
            <div
              className="stamp"
              style={{
                fontSize: 18,
                letterSpacing: "0.3em",
                color: colors.text,
                marginBottom: 4,
              }}
            >
              METHODOLOGY // NOTICE
            </div>
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 10,
                color: colors.textMuted,
                letterSpacing: "0.18em",
              }}
            >
              THE CONFLICT COORDINATE — OPERATIONAL DOSSIER
            </div>
          </div>

          <Section num="01" title="PURPOSE">
            <p style={{ margin: 0, marginBottom: space.sm }}>
              The Conflict Coordinate is a neutral, source-traceable index of
              active global armed conflicts and civil disturbances. Every claim
              rendered on the globe or in a dossier is attributed to a cited
              source. No summary, actor description, or headline is generated
              by a language model.
            </p>
            <p style={{ margin: 0 }}>
              The platform exists as a reference layer — not an editorial
              product. Where ambiguity exists, we show the data and the
              source and let the reader decide.
            </p>
          </Section>

          <Section num="02" title="NEUTRALITY PRINCIPLES">
            <ul
              style={{
                margin: 0,
                paddingLeft: space.lg,
                listStyleType: "'— '",
              }}
            >
              <Rule>
                <strong>No LLM-generated content</strong> in crisis summaries,
                actor descriptions, or source titles. Those fields are authored
                by admins or copied verbatim from cited sources.
              </Rule>
              <Rule>
                <strong>Limited actor roles:</strong> every party linked to a
                crisis is classified as <code>party</code>, <code>mediator</code>,{" "}
                <code>observer</code>, or <code>affected</code>. Loaded terms
                (e.g. "aggressor", "terrorist", "victim") are deliberately
                excluded from the schema.
              </Rule>
              <Rule>
                <strong>Source attribution is mandatory</strong> for every
                actor-to-crisis link added through the admin interface.
              </Rule>
              <Rule>
                <strong>Section labels use descriptive, non-loaded terms</strong>{" "}
                — <code>PARTIES INVOLVED</code>, not <code>COMBATANTS</code>.
              </Rule>
            </ul>
          </Section>

          <Section num="03" title="DATA SOURCES">
            <p style={{ margin: 0, marginBottom: space.md, color: colors.textMuted, fontSize: 13 }}>
              Primary feeds. Each entry has a distinct role in the pipeline.
            </p>
            <div style={{ borderTop: `1px solid ${colors.rule}` }}>
              <SourceRow
                name="ACLED"
                role="[ PRIMARY ]"
                url="https://acleddata.com"
                note="Armed Conflict Location & Event Data. Two distinct feeds: weekly admin1 aggregates (no embargo, ~1–2 weeks behind) supply the globe's dots and every current count; individual geo-coded event records, embargoed ~12 months on the Research tier, supply the incident archive. Data © ACLED, used under academic access and cited on every figure derived from it."
              />
              <SourceRow
                name="GDELT"
                role="[ SUPPLEMENTARY ]"
                url="https://www.gdeltproject.org"
                note="Global news-event stream. Attaches events to existing crises by proximity (< 300 km) to boost coverage in near-real-time."
              />
              <SourceRow
                name="ReliefWeb"
                role="[ CONTEXT ]"
                url="https://reliefweb.int"
                note="OCHA field situation reports, stored per country. The only current narrative layer in the app — the incident archive lags, these do not."
              />
              <SourceRow
                name="UCDP"
                role="[ SUPPLEMENTARY ]"
                url="https://ucdp.uu.se"
                note="Uppsala Conflict Data Program, Georeferenced Event Dataset. Attach-only: events are matched to existing regions and never create their own. Publishes a month or two behind."
              />
              <SourceRow
                name="Wikipedia"
                role="[ BACKGROUND ]"
                url="https://www.wikipedia.org"
                note="Extract API used for actor descriptions and conflict background prose. Text rendered verbatim with citation link."
              />
              <SourceRow
                name="REST Countries"
                role="[ COUNTRY META ]"
                url="https://restcountries.com"
                note="Capital, population, language, and bordering-country data for the country profile strip."
              />
              <SourceRow
                name="Natural Earth"
                role="[ GEO ]"
                url="https://www.naturalearthdata.com"
                note="110m country-border GeoJSON bundled with the client. Used for the optional border overlay on the globe."
              />
            </div>
          </Section>

          <Section num="04" title="INGESTION PIPELINE">
            <p style={{ margin: 0, marginBottom: space.sm }}>
              Ingestion runs on a weekly schedule — the cadence ACLED's
              aggregates publish at, so nothing here can be fresher than that
              — and can also be triggered manually via the admin endpoint.
              Every attempt is recorded, and the footer stamp reports how long
              it has been since one last succeeded. The pipeline is idempotent:
              re-running the same window upserts existing records rather than
              duplicating them.
            </p>
            <ol
              style={{
                fontFamily: fonts.mono,
                fontSize: 12,
                color: colors.textMuted,
                lineHeight: 1.8,
                paddingLeft: space.lg,
                marginTop: space.md,
              }}
            >
              <li>Fetch ACLED events for the configured lookback window.</li>
              <li>Cluster events geographically (DBSCAN, ~100 km radius).</li>
              <li>Upsert cluster → crisis; upsert events → <code>crisis_events</code>.</li>
              <li>Enrich actors + background via Wikipedia; attach ReliefWeb SITREPs.</li>
              <li>Fetch GDELT window; attach events to the nearest crisis.</li>
            </ol>
          </Section>

          <Section num="05" title="KNOWN LIMITATIONS">
            <ul
              style={{ margin: 0, paddingLeft: space.lg, listStyleType: "'— '" }}
            >
              <Rule>
                <strong>Event count ≠ intensity.</strong> The HEX view aggregates
                by event volume, not lethality. A region with many small
                protests will tower over one with fewer high-fatality incidents.
                Cross-reference fatality (†) figures in dossiers for severity.
              </Rule>
              <Rule>
                <strong>ACLED coverage varies by region.</strong> Some states
                report with lag; some journalistic sources are under-represented
                in the feed.
              </Rule>
              <Rule>
                <strong>Clustering is heuristic.</strong> DBSCAN parameters are
                tuned for mid-latitude accuracy; very dense or very sparse
                regions may split or merge imperfectly.
              </Rule>
              <Rule>
                <strong>No forecasting.</strong> All figures reflect past
                reported events only.
              </Rule>
            </ul>
          </Section>

          <Section num="06" title="TECHNICAL STACK">
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 12,
                color: colors.textMuted,
                lineHeight: 1.9,
              }}
            >
              <div>BACKEND · Python 3.12 · FastAPI · SQLAlchemy · Alembic</div>
              <div>DATABASE · PostgreSQL 16 + PostGIS</div>
              <div>FRONTEND · Vite · React 18 · TypeScript · react-globe.gl</div>
              <div>AUTH · Single admin token via <code>X-Admin-Token</code> header</div>
              <div>
                REPO ·{" "}
                <a
                  href="https://github.com/"
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: colors.oliveLight, textDecoration: "none" }}
                >
                  github.com
                </a>
              </div>
            </div>
          </Section>

          <div
            style={{
              textAlign: "center",
              marginTop: space.xxl,
              paddingTop: space.md,
              borderTop: `1px solid ${colors.rule}`,
              fontFamily: fonts.mono,
              fontSize: 10,
              color: colors.textDim,
              letterSpacing: "0.2em",
            }}
          >
            // END OF NOTICE
          </div>
        </div>
      </div>
    </Brief>
  );
}
