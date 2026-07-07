import type {
  Actor,
  ActorRole,
  AdminConflictDetail,
  AdminConflictListItem,
  AdminConflictParty,
  AdminFootprintCell,
  ConflictDetail,
  ConflictListItem,
  ConflictStatus,
  CrisisDetail,
  CrisisEntities,
  CrisisGraph,
  CrisisListItem,
  IngestSummary,
  RoutingRule,
  RoutingRuleType,
  Source,
} from "../types";
import { getAdminToken } from "../lib/adminToken";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { admin?: boolean } = {},
): Promise<T> {
  const { admin, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string> | undefined),
  };
  if (admin) {
    const token = getAdminToken();
    if (token) finalHeaders["X-Admin-Token"] = token;
  }
  const res = await fetch(`${API_URL}${path}`, { ...rest, headers: finalHeaders });
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listConflicts: () => request<ConflictListItem[]>("/api/conflicts"),
  getConflict: (slug: string) =>
    request<ConflictDetail>(`/api/conflicts/${slug}`),
  listCrises: (opts?: { includeLegacy?: boolean }) =>
    request<CrisisListItem[]>(
      `/api/crises${opts?.includeLegacy ? "?include_legacy=true" : ""}`,
    ),
  getCrisis: (slug: string) => request<CrisisDetail>(`/api/crises/${slug}`),
  getCrisisEntities: (slug: string) =>
    request<CrisisEntities>(`/api/crises/${slug}/entities`),
  getCrisisGraph: (slug: string) =>
    request<CrisisGraph>(`/api/crises/${slug}/graph`),
  createCrisis: (payload: Record<string, unknown>) =>
    request<CrisisDetail>("/api/crises", {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  updateCrisis: (slug: string, payload: Record<string, unknown>) =>
    request<CrisisDetail>(`/api/crises/${slug}`, {
      method: "PATCH",
      admin: true,
      body: JSON.stringify(payload),
    }),
  deleteCrisis: (slug: string) =>
    request<void>(`/api/crises/${slug}`, { method: "DELETE", admin: true }),
  linkActor: (slug: string, payload: Record<string, unknown>) =>
    request(`/api/crises/${slug}/actors`, {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  addSource: (slug: string, payload: Record<string, unknown>) =>
    request<Source>(`/api/crises/${slug}/sources`, {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  listActors: () => request<Actor[]>("/api/actors"),
  createActor: (payload: Record<string, unknown>) =>
    request<Actor>("/api/actors", {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  runIngest: () =>
    request<IngestSummary>("/api/ingest/run", { method: "POST", admin: true }),

  // ---- Admin: conflict registry triage -----------------------------------
  listAdminConflicts: () =>
    request<AdminConflictListItem[]>("/api/admin/conflicts", { admin: true }),
  getAdminConflict: (slug: string) =>
    request<AdminConflictDetail>(`/api/admin/conflicts/${slug}`, { admin: true }),
  patchAdminConflict: (
    slug: string,
    payload: Partial<{
      name: string;
      conflict_type: string | null;
      status: ConflictStatus;
      primary_iso3: string | null;
      secondary_iso3s: string[];
      summary: string | null;
      wikipedia_url: string | null;
    }>,
  ) =>
    request<AdminConflictDetail>(`/api/admin/conflicts/${slug}`, {
      method: "PATCH",
      admin: true,
      body: JSON.stringify(payload),
    }),
  deleteAdminConflict: (slug: string) =>
    request<void>(`/api/admin/conflicts/${slug}`, { method: "DELETE", admin: true }),
  addRoutingRule: (
    slug: string,
    payload: { rule_type: RoutingRuleType; pattern: string; priority?: number },
  ) =>
    request<RoutingRule>(`/api/admin/conflicts/${slug}/routing-rules`, {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  deleteRoutingRule: (slug: string, ruleId: number) =>
    request<void>(`/api/admin/conflicts/${slug}/routing-rules/${ruleId}`, {
      method: "DELETE",
      admin: true,
    }),
  addFootprintCell: (
    slug: string,
    payload: { iso3: string; admin1: string; confidence?: number },
  ) =>
    request<AdminFootprintCell>(`/api/admin/conflicts/${slug}/footprint`, {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  deleteFootprintCell: (slug: string, iso3: string, admin1Norm: string) =>
    request<void>(
      `/api/admin/conflicts/${slug}/footprint/${iso3}/${encodeURIComponent(admin1Norm)}`,
      { method: "DELETE", admin: true },
    ),
  addConflictParty: (
    slug: string,
    payload: { actor_id: number; role?: ActorRole; notes?: string | null },
  ) =>
    request<AdminConflictParty>(`/api/admin/conflicts/${slug}/parties`, {
      method: "POST",
      admin: true,
      body: JSON.stringify(payload),
    }),
  removeConflictParty: (slug: string, actorId: number) =>
    request<void>(`/api/admin/conflicts/${slug}/parties/${actorId}`, {
      method: "DELETE",
      admin: true,
    }),
};

export { ApiError };
