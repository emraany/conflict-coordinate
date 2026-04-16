import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import { Brief } from "../components/Brief";
import { StatusChip } from "../components/StatusChip";
import {
  clearAdminToken,
  getAdminToken,
  setAdminToken,
} from "../lib/adminToken";
import { colors, fonts, space } from "../styles/tokens";
import type { Actor, ActorRole, CrisisListItem, CrisisStatus, IngestSummary, SourceType } from "../types";

type Msg = { kind: "ok" | "err"; text: string } | null;

function TokenGate({ onAuthed }: { onAuthed: () => void }) {
  const [value, setValue] = useState("");
  const [msg, setMsg] = useState<Msg>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdminToken(value.trim());
    try {
      await api.listActors();
      onAuthed();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setMsg({ kind: "err", text: "Token rejected" });
      } else {
        setMsg({ kind: "err", text: "API unreachable" });
      }
      clearAdminToken();
    }
  };

  return (
    <form
      onSubmit={submit}
      style={{
        maxWidth: 480,
        margin: "80px auto",
        padding: space.lg,
        border: `1px solid ${colors.ruleStrong}`,
        background: colors.bgRaised,
      }}
    >
      <div
        className="stamp"
        style={{ fontSize: 14, letterSpacing: "0.22em", color: colors.oliveLight }}
      >
        AUTHENTICATION REQUIRED
      </div>
      <p
        className="label"
        style={{
          fontSize: 10,
          color: colors.textMuted,
          marginTop: 4,
          lineHeight: 1.6,
        }}
      >
        ENTER THE ADMIN TOKEN TO ACCESS WRITE OPERATIONS.
      </p>
      <input
        type="password"
        placeholder="X-Admin-Token"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        autoFocus
        style={{ marginTop: space.md }}
      />
      {msg && (
        <div
          style={{
            marginTop: space.sm,
            color: msg.kind === "err" ? colors.active : colors.oliveLight,
            fontSize: 11,
          }}
        >
          {msg.text}
        </div>
      )}
      <button type="submit" style={{ marginTop: space.md, width: "100%" }}>
        Authenticate
      </button>
    </form>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      style={{
        border: `1px solid ${colors.rule}`,
        padding: space.lg,
        background: colors.bgRaised,
      }}
    >
      <div
        className="stamp"
        style={{
          fontSize: 12,
          color: colors.oliveLight,
          letterSpacing: "0.22em",
          paddingBottom: space.sm,
          marginBottom: space.md,
          borderBottom: `1px solid ${colors.rule}`,
        }}
      >
        {title}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span className="label" style={{ fontSize: 10 }}>
        {label}
      </span>
      {children}
    </label>
  );
}

const emptyCrisis = {
  slug: "",
  name: "",
  country: "",
  region: "",
  lat: 0,
  lng: 0,
  summary: "",
  status: "active" as CrisisStatus,
  conflict_type: "",
};

const emptyActor = {
  name: "",
  type: "other",
  description: "",
};

const emptyLink = {
  actor_id: 0,
  role: "party" as ActorRole,
  notes: "",
  source_id: null as number | null,
};

const emptySource = {
  title: "",
  url: "",
  publisher: "",
  source_type: "news" as SourceType,
};

export function AdminPage() {
  const [authed, setAuthed] = useState(!!getAdminToken());
  const [crises, setCrises] = useState<CrisisListItem[]>([]);
  const [actors, setActors] = useState<Actor[]>([]);
  const [msg, setMsg] = useState<Msg>(null);
  const [ingestResult, setIngestResult] = useState<IngestSummary | null>(null);

  const [crisisForm, setCrisisForm] = useState({ ...emptyCrisis });
  const [selectedCrisisSlug, setSelectedCrisisSlug] = useState<string>("");
  const [actorForm, setActorForm] = useState({ ...emptyActor });
  const [linkForm, setLinkForm] = useState({ ...emptyLink });
  const [sourceForm, setSourceForm] = useState({ ...emptySource });

  const refresh = async () => {
    try {
      const [c, a] = await Promise.all([api.listCrises(), api.listActors()]);
      setCrises(c);
      setActors(a);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAdminToken();
        setAuthed(false);
      }
    }
  };

  useEffect(() => {
    if (authed) void refresh();
  }, [authed]);

  if (!authed) {
    return (
      <Brief
        rightMeta={
          <a href="/" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /
          </a>
        }
      >
        <div style={{ overflowY: "auto", height: "100%", width: "100%" }}>
          <TokenGate onAuthed={() => setAuthed(true)} />
        </div>
      </Brief>
    );
  }

  const flash = (ok: boolean, text: string) =>
    setMsg({ kind: ok ? "ok" : "err", text });

  const submitCrisis = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createCrisis({
        ...crisisForm,
        country: crisisForm.country || null,
        region: crisisForm.region || null,
        conflict_type: crisisForm.conflict_type || null,
        summary: crisisForm.summary || null,
      });
      flash(true, `Crisis "${crisisForm.name}" created`);
      setCrisisForm({ ...emptyCrisis });
      await refresh();
    } catch (err) {
      flash(false, err instanceof ApiError ? err.message : "Failed to create crisis");
    }
  };

  const submitActor = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createActor({
        ...actorForm,
        description: actorForm.description || null,
      });
      flash(true, `Actor "${actorForm.name}" created`);
      setActorForm({ ...emptyActor });
      await refresh();
    } catch (err) {
      flash(false, err instanceof ApiError ? err.message : "Failed to create actor");
    }
  };

  const submitLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCrisisSlug || linkForm.actor_id === 0) {
      flash(false, "Select a crisis and an actor");
      return;
    }
    try {
      await api.linkActor(selectedCrisisSlug, {
        actor_id: linkForm.actor_id,
        role: linkForm.role,
        notes: linkForm.notes || null,
        source_id: linkForm.source_id,
      });
      flash(true, "Actor linked");
      setLinkForm({ ...emptyLink });
      await refresh();
    } catch (err) {
      flash(false, err instanceof ApiError ? err.message : "Failed to link actor");
    }
  };

  const submitSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCrisisSlug) {
      flash(false, "Select a crisis first");
      return;
    }
    try {
      await api.addSource(selectedCrisisSlug, {
        ...sourceForm,
        publisher: sourceForm.publisher || null,
      });
      flash(true, "Source attached");
      setSourceForm({ ...emptySource });
    } catch (err) {
      flash(false, err instanceof ApiError ? err.message : "Failed to add source");
    }
  };

  const runIngest = async () => {
    try {
      const r = await api.runIngest();
      setIngestResult(r);
      flash(true, `Ingestion complete: +${r.total_inserted} / ~${r.total_updated}`);
      await refresh();
    } catch (err) {
      flash(false, err instanceof ApiError ? err.message : "Ingestion failed");
    }
  };

  return (
    <Brief
      rightMeta={
        <>
          <a href="/" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /
          </a>
          <button
            onClick={() => {
              clearAdminToken();
              setAuthed(false);
            }}
            style={{ fontSize: 10 }}
          >
            Sign out
          </button>
        </>
      }
    >
      <div
        style={{
          overflowY: "auto",
          height: "100%",
          width: "100%",
          padding: space.lg,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
            gap: space.lg,
            maxWidth: 1400,
            margin: "0 auto",
          }}
        >
          <Section title="CREATE CRISIS">
            <form
              onSubmit={submitCrisis}
              style={{ display: "flex", flexDirection: "column", gap: space.sm }}
            >
              <Field label="Slug (lowercase, hyphens)">
                <input
                  required
                  pattern="[a-z0-9-]+"
                  value={crisisForm.slug}
                  onChange={(e) =>
                    setCrisisForm({ ...crisisForm, slug: e.target.value })
                  }
                />
              </Field>
              <Field label="Name">
                <input
                  required
                  value={crisisForm.name}
                  onChange={(e) =>
                    setCrisisForm({ ...crisisForm, name: e.target.value })
                  }
                />
              </Field>
              <div style={{ display: "flex", gap: space.sm }}>
                <Field label="Country">
                  <input
                    value={crisisForm.country}
                    onChange={(e) =>
                      setCrisisForm({ ...crisisForm, country: e.target.value })
                    }
                  />
                </Field>
                <Field label="Region">
                  <input
                    value={crisisForm.region}
                    onChange={(e) =>
                      setCrisisForm({ ...crisisForm, region: e.target.value })
                    }
                  />
                </Field>
              </div>
              <div style={{ display: "flex", gap: space.sm }}>
                <Field label="Latitude">
                  <input
                    type="number"
                    step="0.0001"
                    required
                    value={crisisForm.lat}
                    onChange={(e) =>
                      setCrisisForm({ ...crisisForm, lat: Number(e.target.value) })
                    }
                  />
                </Field>
                <Field label="Longitude">
                  <input
                    type="number"
                    step="0.0001"
                    required
                    value={crisisForm.lng}
                    onChange={(e) =>
                      setCrisisForm({ ...crisisForm, lng: Number(e.target.value) })
                    }
                  />
                </Field>
              </div>
              <div style={{ display: "flex", gap: space.sm }}>
                <Field label="Status">
                  <select
                    value={crisisForm.status}
                    onChange={(e) =>
                      setCrisisForm({
                        ...crisisForm,
                        status: e.target.value as CrisisStatus,
                      })
                    }
                  >
                    <option value="active">active</option>
                    <option value="frozen">frozen</option>
                    <option value="resolved">resolved</option>
                  </select>
                </Field>
                <Field label="Conflict type">
                  <input
                    value={crisisForm.conflict_type}
                    onChange={(e) =>
                      setCrisisForm({
                        ...crisisForm,
                        conflict_type: e.target.value,
                      })
                    }
                    placeholder="e.g. civil_war, insurgency"
                  />
                </Field>
              </div>
              <Field label="Summary (authored text — no LLM output)">
                <textarea
                  value={crisisForm.summary}
                  onChange={(e) =>
                    setCrisisForm({ ...crisisForm, summary: e.target.value })
                  }
                />
              </Field>
              <button type="submit">Create crisis</button>
            </form>
          </Section>

          <Section title="CREATE ACTOR">
            <form
              onSubmit={submitActor}
              style={{ display: "flex", flexDirection: "column", gap: space.sm }}
            >
              <Field label="Name">
                <input
                  required
                  value={actorForm.name}
                  onChange={(e) =>
                    setActorForm({ ...actorForm, name: e.target.value })
                  }
                />
              </Field>
              <Field label="Type">
                <select
                  value={actorForm.type}
                  onChange={(e) =>
                    setActorForm({ ...actorForm, type: e.target.value })
                  }
                >
                  <option value="state">state</option>
                  <option value="non_state">non_state</option>
                  <option value="coalition">coalition</option>
                  <option value="other">other</option>
                </select>
              </Field>
              <Field label="Description">
                <textarea
                  value={actorForm.description}
                  onChange={(e) =>
                    setActorForm({ ...actorForm, description: e.target.value })
                  }
                />
              </Field>
              <button type="submit">Create actor</button>
            </form>
          </Section>

          <Section title="LINK ACTOR TO CRISIS">
            <form
              onSubmit={submitLink}
              style={{ display: "flex", flexDirection: "column", gap: space.sm }}
            >
              <Field label="Crisis">
                <select
                  required
                  value={selectedCrisisSlug}
                  onChange={(e) => setSelectedCrisisSlug(e.target.value)}
                >
                  <option value="">— select —</option>
                  {crises.map((c) => (
                    <option key={c.slug} value={c.slug}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Actor">
                <select
                  required
                  value={linkForm.actor_id}
                  onChange={(e) =>
                    setLinkForm({
                      ...linkForm,
                      actor_id: Number(e.target.value),
                    })
                  }
                >
                  <option value={0}>— select —</option>
                  {actors.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Role">
                <select
                  value={linkForm.role}
                  onChange={(e) =>
                    setLinkForm({
                      ...linkForm,
                      role: e.target.value as ActorRole,
                    })
                  }
                >
                  <option value="party">party</option>
                  <option value="mediator">mediator</option>
                  <option value="observer">observer</option>
                  <option value="affected">affected</option>
                </select>
              </Field>
              <Field label="Attributing source ID (recommended)">
                <input
                  type="number"
                  value={linkForm.source_id ?? ""}
                  onChange={(e) =>
                    setLinkForm({
                      ...linkForm,
                      source_id: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </Field>
              <Field label="Notes">
                <textarea
                  value={linkForm.notes}
                  onChange={(e) =>
                    setLinkForm({ ...linkForm, notes: e.target.value })
                  }
                />
              </Field>
              <button type="submit">Link actor</button>
            </form>
          </Section>

          <Section title="ATTACH SOURCE TO CRISIS">
            <form
              onSubmit={submitSource}
              style={{ display: "flex", flexDirection: "column", gap: space.sm }}
            >
              <Field label="Crisis">
                <select
                  required
                  value={selectedCrisisSlug}
                  onChange={(e) => setSelectedCrisisSlug(e.target.value)}
                >
                  <option value="">— select —</option>
                  {crises.map((c) => (
                    <option key={c.slug} value={c.slug}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Title">
                <input
                  required
                  value={sourceForm.title}
                  onChange={(e) =>
                    setSourceForm({ ...sourceForm, title: e.target.value })
                  }
                />
              </Field>
              <Field label="URL">
                <input
                  required
                  type="url"
                  value={sourceForm.url}
                  onChange={(e) =>
                    setSourceForm({ ...sourceForm, url: e.target.value })
                  }
                />
              </Field>
              <Field label="Publisher">
                <input
                  value={sourceForm.publisher}
                  onChange={(e) =>
                    setSourceForm({ ...sourceForm, publisher: e.target.value })
                  }
                />
              </Field>
              <Field label="Source type">
                <select
                  value={sourceForm.source_type}
                  onChange={(e) =>
                    setSourceForm({
                      ...sourceForm,
                      source_type: e.target.value as SourceType,
                    })
                  }
                >
                  <option value="news">news</option>
                  <option value="report">report</option>
                  <option value="academic">academic</option>
                  <option value="official">official</option>
                  <option value="primary">primary</option>
                </select>
              </Field>
              <button type="submit">Attach source</button>
            </form>
          </Section>

          <Section title="RUN INGESTION">
            <p
              className="label"
              style={{ fontSize: 10, lineHeight: 1.6, marginBottom: space.md }}
            >
              EXECUTES ALL REGISTERED INGESTION SOURCES (FIXTURE + ACLED STUB).
              IDEMPOTENT — UPSERTS BY (source_name, external_id).
            </p>
            <button onClick={runIngest}>Run ingestion</button>
            {ingestResult && (
              <pre
                style={{
                  marginTop: space.md,
                  padding: space.sm,
                  background: colors.bg,
                  border: `1px solid ${colors.rule}`,
                  fontSize: 11,
                  color: colors.text,
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(ingestResult, null, 2)}
              </pre>
            )}
          </Section>

          <Section title="CRISIS INVENTORY">
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: space.xs,
                fontFamily: fonts.mono,
                fontSize: 12,
              }}
            >
              {crises.map((c) => (
                <div
                  key={c.slug}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: space.sm,
                    padding: "4px 0",
                    borderBottom: `1px dashed ${colors.rule}`,
                  }}
                >
                  <span>{c.name}</span>
                  <StatusChip status={c.status} />
                </div>
              ))}
              {crises.length === 0 && (
                <span className="label" style={{ color: colors.textDim }}>
                  (none)
                </span>
              )}
            </div>
          </Section>
        </div>

        {msg && (
          <div
            style={{
              position: "fixed",
              top: 56,
              right: space.md,
              background: colors.bgRaised,
              border: `1px solid ${msg.kind === "ok" ? colors.oliveLight : colors.active}`,
              padding: `${space.sm}px ${space.md}px`,
              color: msg.kind === "ok" ? colors.oliveLight : colors.active,
              fontSize: 11,
              letterSpacing: "0.1em",
            }}
          >
            <span className="stamp">{msg.kind === "ok" ? "OK" : "ERR"}</span> — {msg.text}
          </div>
        )}
      </div>
    </Brief>
  );
}
