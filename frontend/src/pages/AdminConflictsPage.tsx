import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { Brief } from "../components/Brief";
import { StatusChip } from "../components/StatusChip";
import {
  clearAdminToken,
  getAdminToken,
  setAdminToken,
} from "../lib/adminToken";
import { colors, fonts, space, statusColor } from "../styles/tokens";
import type {
  Actor,
  ActorRole,
  AdminConflictDetail,
  AdminConflictListItem,
  AdminConflictParty,
  AdminFootprintCell,
  ConflictStatus,
  RoutingRule,
  RoutingRuleType,
} from "../types";

type Msg = { kind: "ok" | "err"; text: string } | null;

function TokenGate({ onAuthed }: { onAuthed: () => void }) {
  const [value, setValue] = useState("");
  const [msg, setMsg] = useState<Msg>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setAdminToken(value.trim());
    try {
      await api.listAdminConflicts();
      onAuthed();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setMsg({ kind: "err", text: "Token rejected" });
      } else {
        setMsg({ kind: "err", text: "API unreachable" });
      }
      clearAdminToken();
    }
  }

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
      <div className="stamp" style={{ fontSize: 14, letterSpacing: "0.22em", color: colors.oliveLight }}>
        AUTHENTICATION REQUIRED
      </div>
      <p style={{ fontSize: 10, color: colors.textMuted, marginTop: 4, lineHeight: 1.6 }}>
        Provide the admin token to triage emerging conflicts.
      </p>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="X-Admin-Token"
        style={{
          width: "100%",
          background: colors.bgSunken,
          border: `1px solid ${colors.rule}`,
          color: colors.text,
          fontFamily: fonts.mono,
          fontSize: 12,
          padding: 8,
          marginTop: space.md,
          outline: "none",
        }}
      />
      <button
        type="submit"
        style={{
          marginTop: space.md,
          background: colors.oliveDim,
          border: `1px solid ${colors.olive}`,
          color: colors.oliveLight,
          fontFamily: fonts.mono,
          fontSize: 11,
          letterSpacing: "0.18em",
          padding: "6px 16px",
          cursor: "pointer",
        }}
      >
        [ AUTHENTICATE ]
      </button>
      {msg && (
        <div
          style={{
            marginTop: space.md,
            fontFamily: fonts.mono,
            fontSize: 11,
            color: msg.kind === "err" ? colors.active : colors.oliveLight,
          }}
        >
          {msg.text}
        </div>
      )}
    </form>
  );
}

const inputStyle = {
  background: colors.bgSunken,
  border: `1px solid ${colors.rule}`,
  color: colors.text,
  fontFamily: fonts.mono,
  fontSize: 11,
  padding: "4px 8px",
  outline: "none",
  width: "100%",
} as const;

const labelStyle = {
  fontFamily: fonts.mono,
  fontSize: 9,
  letterSpacing: "0.18em",
  color: colors.textMuted,
  display: "block",
  marginBottom: 4,
} as const;

const btn = (variant: "primary" | "neutral" | "danger" = "neutral") => {
  const base = {
    fontFamily: fonts.mono,
    fontSize: 10,
    letterSpacing: "0.16em",
    padding: "4px 12px",
    cursor: "pointer",
    background: "transparent" as string,
    border: `1px solid ${colors.rule}` as string,
    color: colors.textMuted as string,
  };
  if (variant === "primary")
    return { ...base, border: `1px solid ${colors.olive}`, color: colors.oliveLight };
  if (variant === "danger")
    return { ...base, border: `1px solid ${colors.active}`, color: colors.active };
  return base;
};

function CuratePanel({
  detail,
  actorCatalog,
  onClose,
  onChanged,
}: {
  detail: AdminConflictDetail;
  actorCatalog: Actor[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [name, setName] = useState(detail.name);
  const [primaryIso3, setPrimaryIso3] = useState(detail.primary_iso3 ?? "");
  const [conflictType, setConflictType] = useState(detail.conflict_type ?? "");
  const [summary, setSummary] = useState(detail.summary ?? "");
  const [rulePattern, setRulePattern] = useState("");
  const [ruleType, setRuleType] = useState<RoutingRuleType>("country");
  const [fpIso3, setFpIso3] = useState("");
  const [fpAdmin1, setFpAdmin1] = useState("");
  const [partyActorId, setPartyActorId] = useState<number | "">("");
  const [partyRole, setPartyRole] = useState<ActorRole>("party");
  const [partyActorSearch, setPartyActorSearch] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);

  // Local copies so add/delete reflect without re-fetch.
  const [rules, setRules] = useState<RoutingRule[]>(detail.routing_rules);
  const [footprints, setFootprints] = useState<AdminFootprintCell[]>(detail.footprints);
  const [parties, setParties] = useState<AdminConflictParty[]>(detail.parties);

  const partyActorOptions = useMemo(() => {
    const linkedIds = new Set(parties.map((p) => p.actor.id));
    const q = partyActorSearch.trim().toLowerCase();
    return actorCatalog
      .filter((a) => !linkedIds.has(a.id))
      .filter((a) => (q === "" ? true : a.name.toLowerCase().includes(q)))
      .slice(0, 50);
  }, [actorCatalog, parties, partyActorSearch]);

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await api.patchAdminConflict(detail.slug, {
        name,
        primary_iso3: primaryIso3 || null,
        conflict_type: conflictType || null,
        summary: summary || null,
      });
      setMsg({ kind: "ok", text: "Saved" });
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(next: ConflictStatus) {
    setBusy(true);
    setMsg(null);
    try {
      await api.patchAdminConflict(detail.slug, { status: next });
      setMsg({ kind: "ok", text: `Status → ${next}` });
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Status change failed" });
    } finally {
      setBusy(false);
    }
  }

  async function addRule() {
    if (!rulePattern.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const rule = await api.addRoutingRule(detail.slug, {
        rule_type: ruleType,
        pattern: rulePattern.trim(),
      });
      setRules((r) => [...r, rule]);
      setRulePattern("");
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Rule add failed" });
    } finally {
      setBusy(false);
    }
  }

  async function removeRule(ruleId: number) {
    setBusy(true);
    setMsg(null);
    try {
      await api.deleteRoutingRule(detail.slug, ruleId);
      setRules((r) => r.filter((x) => x.id !== ruleId));
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Rule delete failed" });
    } finally {
      setBusy(false);
    }
  }

  async function destroy() {
    if (!window.confirm(`Delete "${detail.name}"? Events will be detached for re-routing.`)) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.deleteAdminConflict(detail.slug);
      onChanged();
      onClose();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Delete failed" });
    } finally {
      setBusy(false);
    }
  }

  async function addFootprint() {
    if (!fpIso3.trim() || !fpAdmin1.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const cell = await api.addFootprintCell(detail.slug, {
        iso3: fpIso3.trim().toUpperCase(),
        admin1: fpAdmin1.trim(),
      });
      setFootprints((f) => [...f, cell]);
      // The backend also creates a matching admin1 routing rule. Refresh the
      // rules list by re-fetching the detail.
      const fresh = await api.getAdminConflict(detail.slug);
      setRules(fresh.routing_rules);
      setFpIso3("");
      setFpAdmin1("");
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Footprint add failed" });
    } finally {
      setBusy(false);
    }
  }

  async function removeFootprint(iso3: string, admin1Norm: string) {
    setBusy(true);
    setMsg(null);
    try {
      await api.deleteFootprintCell(detail.slug, iso3, admin1Norm);
      setFootprints((f) =>
        f.filter((c) => !(c.country_iso3 === iso3 && c.admin1_norm === admin1Norm)),
      );
      // The implied admin1 routing rule is also dropped — refresh.
      const fresh = await api.getAdminConflict(detail.slug);
      setRules(fresh.routing_rules);
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Footprint drop failed" });
    } finally {
      setBusy(false);
    }
  }

  async function addParty() {
    if (partyActorId === "") return;
    setBusy(true);
    setMsg(null);
    try {
      const link = await api.addConflictParty(detail.slug, {
        actor_id: partyActorId as number,
        role: partyRole,
      });
      setParties((p) => [...p, link]);
      setPartyActorId("");
      setPartyActorSearch("");
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Party add failed" });
    } finally {
      setBusy(false);
    }
  }

  async function removeParty(actorId: number) {
    setBusy(true);
    setMsg(null);
    try {
      await api.removeConflictParty(detail.slug, actorId);
      setParties((p) => p.filter((x) => x.actor.id !== actorId));
      onChanged();
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Party remove failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        bottom: 0,
        width: 560,
        background: colors.bgRaised,
        borderLeft: `1px solid ${colors.ruleStrong}`,
        padding: space.lg,
        overflowY: "auto",
        zIndex: 100,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: space.md }}>
        <div className="stamp" style={{ fontSize: 13, letterSpacing: "0.22em", color: colors.oliveLight }}>
          CURATE
        </div>
        <button onClick={onClose} style={btn()}>
          [ CLOSE ]
        </button>
      </div>

      <div style={{ display: "flex", gap: space.md, alignItems: "baseline", marginBottom: space.md }}>
        <StatusChip status={detail.status} />
        <span style={{ fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
          {detail.registry_source} · events={detail.event_count} · 4w={detail.intensity_4w_events}
        </span>
      </div>

      {detail.wikipedia_url && (
        <a
          href={detail.wikipedia_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontFamily: fonts.mono,
            fontSize: 10,
            color: colors.oliveLight,
            textDecoration: "none",
            display: "block",
            marginBottom: space.md,
          }}
        >
          [ READ ON WIKIPEDIA ]
        </a>
      )}

      <div style={{ marginBottom: space.md }}>
        <label style={labelStyle}>NAME</label>
        <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />
      </div>

      <div style={{ display: "flex", gap: space.md, marginBottom: space.md }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>PRIMARY ISO3</label>
          <input
            value={primaryIso3}
            onChange={(e) => setPrimaryIso3(e.target.value.toUpperCase().slice(0, 3))}
            placeholder="e.g. IRN"
            style={inputStyle}
          />
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>CONFLICT TYPE</label>
          <input
            value={conflictType}
            onChange={(e) => setConflictType(e.target.value)}
            placeholder="e.g. asymmetric"
            style={inputStyle}
          />
        </div>
      </div>

      <div style={{ marginBottom: space.md }}>
        <label style={labelStyle}>SUMMARY</label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={6}
          style={{ ...inputStyle, resize: "vertical" as const, fontSize: 11, lineHeight: 1.5 }}
        />
      </div>

      <div style={{ display: "flex", gap: space.sm, marginBottom: space.lg }}>
        <button onClick={save} disabled={busy} style={btn("primary")}>
          [ SAVE ]
        </button>
        {detail.status !== "active" && (
          <button onClick={() => setStatus("active")} disabled={busy} style={btn("primary")}>
            [ PROMOTE → ACTIVE ]
          </button>
        )}
        {detail.status === "active" && (
          <button onClick={() => setStatus("frozen")} disabled={busy} style={btn()}>
            [ DEMOTE → FROZEN ]
          </button>
        )}
        <button onClick={destroy} disabled={busy} style={btn("danger")}>
          [ DELETE ]
        </button>
      </div>

      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: "0.18em",
          color: colors.textMuted,
          marginBottom: space.sm,
          borderBottom: `1px solid ${colors.rule}`,
          paddingBottom: 4,
        }}
      >
        ROUTING RULES · {rules.length}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: space.md }}>
        <thead>
          <tr>
            {(["TYPE", "PATTERN", "PRI", ""] as const).map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i === 3 ? "right" : "left",
                  fontFamily: fonts.mono,
                  fontSize: 9,
                  color: colors.textDim,
                  padding: "4px 0",
                  borderBottom: `1px solid ${colors.rule}`,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rules.length === 0 && (
            <tr>
              <td
                colSpan={4}
                style={{
                  padding: "8px 0",
                  fontFamily: fonts.mono,
                  fontSize: 10,
                  color: colors.textDim,
                }}
              >
                // no routing rules yet — events cannot reach this conflict
              </td>
            </tr>
          )}
          {rules.map((r) => (
            <tr key={r.id}>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted }}>
                {r.rule_type}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.text }}>
                {r.pattern}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                {r.priority}
              </td>
              <td style={{ padding: "4px 0", textAlign: "right" }}>
                <button onClick={() => removeRule(r.id)} disabled={busy} style={btn("danger")}>
                  [ DROP ]
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "100px 1fr auto",
          gap: space.sm,
          alignItems: "end",
        }}
      >
        <div>
          <label style={labelStyle}>TYPE</label>
          <select
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value as RoutingRuleType)}
            style={{ ...inputStyle, cursor: "pointer" }}
          >
            <option value="country">country</option>
            <option value="admin1">admin1</option>
            <option value="actor">actor</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>PATTERN</label>
          <input
            value={rulePattern}
            onChange={(e) => setRulePattern(e.target.value)}
            placeholder={
              ruleType === "country"
                ? "ISO3 e.g. IRN"
                : ruleType === "admin1"
                  ? "IRN:tehran"
                  : "Houthi%"
            }
            style={inputStyle}
          />
        </div>
        <button onClick={addRule} disabled={busy} style={btn("primary")}>
          [ ADD RULE ]
        </button>
      </div>

      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: "0.18em",
          color: colors.textMuted,
          marginTop: space.lg,
          marginBottom: space.sm,
          borderBottom: `1px solid ${colors.rule}`,
          paddingBottom: 4,
        }}
      >
        FOOTPRINT CELLS · {footprints.length}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: space.md }}>
        <thead>
          <tr>
            {(["ISO3", "ADMIN1 (NORM)", "CONF", ""] as const).map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i === 3 ? "right" : "left",
                  fontFamily: fonts.mono,
                  fontSize: 9,
                  color: colors.textDim,
                  padding: "4px 0",
                  borderBottom: `1px solid ${colors.rule}`,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {footprints.length === 0 && (
            <tr>
              <td colSpan={4} style={{ padding: "6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                // no footprint cells — only country / actor routing applies
              </td>
            </tr>
          )}
          {footprints.map((f) => (
            <tr key={`${f.country_iso3}:${f.admin1_norm}`}>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.text }}>
                {f.country_iso3}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted }}>
                {f.admin1_norm}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                {f.confidence.toFixed(2)}
              </td>
              <td style={{ padding: "4px 0", textAlign: "right" }}>
                <button
                  onClick={() => removeFootprint(f.country_iso3, f.admin1_norm)}
                  disabled={busy}
                  style={btn("danger")}
                >
                  [ DROP ]
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: "grid", gridTemplateColumns: "70px 1fr auto", gap: space.sm, alignItems: "end" }}>
        <div>
          <label style={labelStyle}>ISO3</label>
          <input
            value={fpIso3}
            onChange={(e) => setFpIso3(e.target.value.toUpperCase().slice(0, 3))}
            placeholder="IRN"
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>ADMIN1 (display form)</label>
          <input
            value={fpAdmin1}
            onChange={(e) => setFpAdmin1(e.target.value)}
            placeholder="Hormozgan"
            style={inputStyle}
          />
        </div>
        <button onClick={addFootprint} disabled={busy} style={btn("primary")}>
          [ ADD CELL ]
        </button>
      </div>

      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: "0.18em",
          color: colors.textMuted,
          marginTop: space.lg,
          marginBottom: space.sm,
          borderBottom: `1px solid ${colors.rule}`,
          paddingBottom: 4,
        }}
      >
        PARTIES · {parties.length}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: space.md }}>
        <thead>
          <tr>
            {(["ACTOR", "ROLE", "TYPE", ""] as const).map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i === 3 ? "right" : "left",
                  fontFamily: fonts.mono,
                  fontSize: 9,
                  color: colors.textDim,
                  padding: "4px 0",
                  borderBottom: `1px solid ${colors.rule}`,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {parties.length === 0 && (
            <tr>
              <td colSpan={4} style={{ padding: "6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                // no parties attached yet
              </td>
            </tr>
          )}
          {parties.map((p) => (
            <tr key={p.actor.id}>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.text }}>
                {p.actor.name}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted }}>
                {p.role}
              </td>
              <td style={{ padding: "4px 8px 4px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
                {p.actor.type}
              </td>
              <td style={{ padding: "4px 0", textAlign: "right" }}>
                <button onClick={() => removeParty(p.actor.id)} disabled={busy} style={btn("danger")}>
                  [ DROP ]
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 110px auto", gap: space.sm, alignItems: "end" }}>
        <div>
          <label style={labelStyle}>ACTOR ({partyActorOptions.length} match)</label>
          <input
            value={partyActorSearch}
            onChange={(e) => setPartyActorSearch(e.target.value)}
            placeholder="search canon..."
            style={inputStyle}
          />
          <select
            value={partyActorId === "" ? "" : String(partyActorId)}
            onChange={(e) =>
              setPartyActorId(e.target.value === "" ? "" : Number(e.target.value))
            }
            style={{ ...inputStyle, cursor: "pointer", marginTop: 4 }}
          >
            <option value="">— pick actor —</option>
            {partyActorOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={labelStyle}>ROLE</label>
          <select
            value={partyRole}
            onChange={(e) => setPartyRole(e.target.value as ActorRole)}
            style={{ ...inputStyle, cursor: "pointer" }}
          >
            <option value="party">party</option>
            <option value="mediator">mediator</option>
            <option value="observer">observer</option>
            <option value="affected">affected</option>
          </select>
        </div>
        <button onClick={addParty} disabled={busy || partyActorId === ""} style={btn("primary")}>
          [ LINK ]
        </button>
      </div>

      {msg && (
        <div
          style={{
            marginTop: space.md,
            fontFamily: fonts.mono,
            fontSize: 11,
            color: msg.kind === "err" ? colors.active : colors.oliveLight,
          }}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}

function ConflictRow({
  c,
  onSelect,
}: {
  c: AdminConflictListItem;
  onSelect: (slug: string) => void;
}) {
  const accent = statusColor(c.status);
  return (
    <tr
      onClick={() => onSelect(c.slug)}
      style={{ cursor: "pointer", transition: "background 120ms" }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.background = `color-mix(in srgb, ${colors.oliveLight} 7%, transparent)`)
      }
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 12, color: colors.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {c.name}
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: accent, whiteSpace: "nowrap" }}>
        [ {c.status.toUpperCase()} ]
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted }}>
        {c.primary_iso3 ?? "—"}
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 10, color: colors.textDim }}>
        {c.registry_source}
        {c.admin_curated && " · curated"}
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted, textAlign: "right" }}>
        {c.routing_rule_count}
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 11, color: colors.textMuted, textAlign: "right" }}>
        {c.event_count.toLocaleString()}
      </td>
      <td style={{ padding: "6px 10px 6px 0", fontFamily: fonts.mono, fontSize: 11, color: c.intensity_4w_events > 0 ? colors.oliveLight : colors.textDim, textAlign: "right" }}>
        {c.intensity_4w_events.toLocaleString()}
      </td>
    </tr>
  );
}

function AdminConflictsBody() {
  const [conflicts, setConflicts] = useState<AdminConflictListItem[]>([]);
  const [actorCatalog, setActorCatalog] = useState<Actor[]>([]);
  const [statusFilter, setStatusFilter] = useState<ConflictStatus | "all">("emerging");
  const [search, setSearch] = useState("");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminConflictDetail | null>(null);

  const reload = useCallback(async () => {
    try {
      const rows = await api.listAdminConflicts();
      setConflicts(rows);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    reload();
    // Actor catalog rarely changes — fetch once.
    api.listActors().then(setActorCatalog).catch(console.error);
  }, [reload]);

  useEffect(() => {
    if (selectedSlug === null) {
      setDetail(null);
      return;
    }
    let cancel = false;
    api
      .getAdminConflict(selectedSlug)
      .then((d) => {
        if (!cancel) setDetail(d);
      })
      .catch(console.error);
    return () => {
      cancel = true;
    };
  }, [selectedSlug]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return conflicts.filter(
      (c) =>
        (statusFilter === "all" || c.status === statusFilter) &&
        (q === "" ||
          c.name.toLowerCase().includes(q) ||
          (c.primary_iso3 ?? "").toLowerCase().includes(q) ||
          c.slug.includes(q)),
    );
  }, [conflicts, search, statusFilter]);

  async function handleDetailChanged() {
    await reload();
    if (selectedSlug) {
      try {
        const d = await api.getAdminConflict(selectedSlug);
        setDetail(d);
      } catch {
        setSelectedSlug(null);
      }
    }
  }

  const counts = useMemo(() => {
    const out: Record<string, number> = { all: conflicts.length };
    for (const c of conflicts) out[c.status] = (out[c.status] ?? 0) + 1;
    return out;
  }, [conflicts]);

  return (
    <Brief
      section="admin"
      rightMeta={
        <>
          <a href="/admin" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /admin
          </a>
          <a href="/" style={{ color: colors.textMuted, textDecoration: "none" }}>
            /map
          </a>
        </>
      }
    >
      {detail && (
        <CuratePanel
          detail={detail}
          actorCatalog={actorCatalog}
          onClose={() => setSelectedSlug(null)}
          onChanged={handleDetailChanged}
        />
      )}

      <div style={{ height: "100%", overflowY: "auto", padding: `${space.lg}px ${space.xl}px`, marginRight: detail ? 560 : 0 }}>
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
          <span className="stamp" style={{ fontSize: 14, letterSpacing: "0.22em", color: colors.text }}>
            CONFLICT TRIAGE
          </span>
          <span style={{ fontFamily: fonts.mono, fontSize: 10, color: colors.textMuted }}>
            {counts.emerging ?? 0} EMERGING · {counts.active ?? 0} ACTIVE · {counts.frozen ?? 0} FROZEN
          </span>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: space.lg,
            marginBottom: space.lg,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em", fontFamily: fonts.mono }}>
              SEARCH
            </span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="name, iso3, slug..."
              style={{ ...inputStyle, width: 280 }}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: space.sm }}>
            <span style={{ fontSize: 9, color: colors.textDim, letterSpacing: "0.16em", fontFamily: fonts.mono }}>
              STATUS
            </span>
            {(["emerging", "active", "frozen", "resolved", "all"] as const).map((s) => {
              const on = statusFilter === s;
              const c = s === "all" ? colors.oliveLight : statusColor(s);
              return (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  style={{
                    background: on ? `color-mix(in srgb, ${c} 14%, ${colors.bg})` : "transparent",
                    border: `1px solid ${on ? c : colors.rule}`,
                    color: on ? c : colors.textDim,
                    fontFamily: fonts.mono,
                    fontSize: 10,
                    letterSpacing: "0.18em",
                    padding: "3px 10px",
                    cursor: "pointer",
                  }}
                >
                  [ {s.toUpperCase()} {counts[s] ? `· ${counts[s]}` : ""} ]
                </button>
              );
            })}
          </div>
        </div>

        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "auto" }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 70 }} />
            <col style={{ width: 130 }} />
            <col style={{ width: 60 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr>
              {[
                ["NAME", "left"],
                ["STATUS", "left"],
                ["ISO3", "left"],
                ["SOURCE", "left"],
                ["RULES", "right"],
                ["EVENTS", "right"],
                ["4W", "right"],
              ].map(([lbl, align]) => (
                <th
                  key={lbl}
                  style={{
                    textAlign: align as "left" | "right",
                    fontFamily: fonts.mono,
                    fontSize: 9,
                    letterSpacing: "0.18em",
                    color: colors.textMuted,
                    borderBottom: `1px solid ${colors.rule}`,
                    padding: "5px 10px 5px 0",
                  }}
                >
                  {lbl}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  style={{
                    padding: space.lg,
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    color: colors.textMuted,
                  }}
                >
                  // NO CONFLICTS MATCH FILTER
                </td>
              </tr>
            )}
            {filtered.map((c) => (
              <ConflictRow key={c.slug} c={c} onSelect={setSelectedSlug} />
            ))}
          </tbody>
        </table>
      </div>
    </Brief>
  );
}

export function AdminConflictsPage() {
  const [authed, setAuthed] = useState(() => Boolean(getAdminToken()));
  if (!authed) return <TokenGate onAuthed={() => setAuthed(true)} />;
  return <AdminConflictsBody />;
}
