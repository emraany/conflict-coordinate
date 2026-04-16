import type {
  Actor,
  CrisisDetail,
  CrisisListItem,
  IngestSummary,
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
  listCrises: () => request<CrisisListItem[]>("/api/crises"),
  getCrisis: (slug: string) => request<CrisisDetail>(`/api/crises/${slug}`),
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
};

export { ApiError };
