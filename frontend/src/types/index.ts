// Mirror of backend Pydantic schemas. Keep field names in sync with
// backend/app/schemas/*.py.

export type CrisisStatus = "active" | "frozen" | "resolved";
export type ActorRole = "party" | "mediator" | "observer" | "affected";
export type ActorType = "state" | "non_state" | "coalition" | "other";
export type SourceType =
  | "news"
  | "report"
  | "academic"
  | "official"
  | "primary"
  | "situation_report"
  | "reference";

export interface Actor {
  id: number;
  name: string;
  type: ActorType;
  description: string | null;
  wikipedia_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Source {
  id: number;
  crisis_id: number | null;
  title: string;
  url: string;
  publisher: string | null;
  published_at: string | null;
  retrieved_at: string | null;
  source_type: SourceType;
  origin: string | null;
  body_text: string | null;
  created_at: string;
}

export interface ActorLink {
  actor: Actor;
  role: ActorRole;
  notes: string | null;
  source_id: number | null;
}

export interface CrisisEvent {
  id: number;
  crisis_id: number;
  occurred_at: string;
  event_type: string | null;
  description: string | null;
  fatalities: number | null;
  location_name: string | null;
  lat: number | null;
  lng: number | null;
  source_id: number | null;
  created_at: string;
}

export interface CrisisListItem {
  id: number;
  slug: string;
  name: string;
  country: string | null;
  lat: number;
  lng: number;
  status: CrisisStatus;
  conflict_type: string | null;
}

export interface CrisisStats {
  total_events: number;
  total_fatalities: number;
  event_type_counts: Record<string, number>;
  first_event_at: string | null;
  last_event_at: string | null;
}

export interface CrisisDetail {
  id: number;
  slug: string;
  name: string;
  country: string | null;
  region: string | null;
  lat: number;
  lng: number;
  summary: string | null;
  status: CrisisStatus;
  conflict_type: string | null;
  started_at: string | null;
  last_event_at: string | null;
  external_id: string | null;
  source_name: string | null;
  created_at: string;
  updated_at: string;
  actors: ActorLink[];
  sources: Source[];
  events: CrisisEvent[];
  stats: CrisisStats;
}

export interface IngestSummary {
  sources: { source: string; inserted: number; updated: number }[];
  total_inserted: number;
  total_updated: number;
}
