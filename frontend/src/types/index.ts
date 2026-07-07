// Mirror of backend Pydantic schemas. Keep field names in sync with
// backend/app/schemas/*.py.

export type CrisisStatus = "active" | "frozen" | "resolved";
export type ConflictStatus = "active" | "frozen" | "resolved" | "emerging";
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
  country_iso3: string | null;
  admin1: string | null;
  region: string | null;
  lat: number;
  lng: number;
  status: CrisisStatus;
  conflict_type: string | null;
  started_at: string | null;
  last_event_at: string | null;
  event_count: number;
  total_fatalities: number;
}

export interface CrisisStats {
  total_events: number;
  total_fatalities: number;
  event_type_counts: Record<string, number>;
  first_event_at: string | null;
  last_event_at: string | null;
  recent_4w_events: number;
  recent_4w_fatalities: number;
  recent_population_exposed: number | null;
}

export interface IntensityWeek {
  week_start: string; // ISO date
  event_count_by_type: Record<string, number>;
  fatalities: number;
  population_exposure: number | null;
}

export interface CrisisDetail {
  id: number;
  slug: string;
  name: string;
  country: string | null;
  country_iso3: string | null;
  admin1: string | null;
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
  intensity_52w: IntensityWeek[];
}

export interface IngestSummary {
  sources: { source: string; inserted: number; updated: number }[];
  total_inserted: number;
  total_updated: number;
}

// ---- Conflict registry (new dot-on-globe entity) -----------------------

export interface ConflictListItem {
  id: number;
  slug: string;
  name: string;
  conflict_type: string | null;
  status: ConflictStatus;
  primary_iso3: string | null;
  secondary_iso3s: string[];
  lat: number | null;
  lng: number | null;
  started_at: string | null;
  last_event_at: string | null;
  intensity_4w_events: number;
  intensity_4w_fatalities: number;
  event_count: number;
  total_fatalities: number;
}

export interface ConflictParty {
  actor: Actor;
  role: ActorRole;
  notes: string | null;
  source_id: number | null;
}

export interface ConflictStats {
  total_events: number;
  total_fatalities: number;
  event_type_counts: Record<string, number>;
  first_event_at: string | null;
  last_event_at: string | null;
  recent_4w_events: number;
  recent_4w_fatalities: number;
}

export interface TopAdmin1 {
  iso3: string;
  admin1: string;
  event_count: number;
}

export interface ConflictDetail {
  id: number;
  slug: string;
  name: string;
  conflict_type: string | null;
  status: ConflictStatus;
  primary_iso3: string | null;
  secondary_iso3s: string[];
  lat: number | null;
  lng: number | null;
  started_at: string | null;
  resolved_at: string | null;
  last_event_at: string | null;
  summary: string | null;
  wikipedia_url: string | null;
  ucdp_conflict_id: string | null;
  parties: ConflictParty[];
  events: CrisisEvent[];
  sources: Source[];
  stats: ConflictStats;
  intensity_52w: IntensityWeek[];
  top_admin1s: TopAdmin1[];
  created_at: string;
  updated_at: string;
}

// ---- Admin: conflict-registry triage -----------------------------------

export type RoutingRuleType = "actor" | "admin1" | "country";

export interface RoutingRule {
  id: number;
  rule_type: RoutingRuleType;
  pattern: string;
  priority: number;
}

export interface AdminConflictListItem {
  id: number;
  slug: string;
  name: string;
  conflict_type: string | null;
  status: ConflictStatus;
  primary_iso3: string | null;
  secondary_iso3s: string[];
  summary: string | null;
  wikipedia_url: string | null;
  registry_source: string;
  admin_curated: boolean;
  event_count: number;
  intensity_4w_events: number;
  routing_rule_count: number;
  last_event_at: string | null;
}

export interface AdminConflictDetail {
  id: number;
  slug: string;
  name: string;
  conflict_type: string | null;
  status: ConflictStatus;
  primary_iso3: string | null;
  secondary_iso3s: string[];
  summary: string | null;
  wikipedia_url: string | null;
  registry_source: string;
  admin_curated: boolean;
  event_count: number;
  intensity_4w_events: number;
  routing_rules: RoutingRule[];
  footprints: AdminFootprintCell[];
  parties: AdminConflictParty[];
  last_event_at: string | null;
}

export interface AdminFootprintCell {
  country_iso3: string;
  admin1_norm: string;
  confidence: number;
}

export interface AdminConflictParty {
  actor: { id: number; name: string; type: string };
  role: ActorRole;
  notes: string | null;
}

export interface EntityAggregate {
  label: string;
  text: string;
  count: number;
  event_ids: number[];
}

export interface EntityGroup {
  label: string;
  entities: EntityAggregate[];
}

export interface CrisisEntities {
  crisis_id: number;
  total_mentions: number;
  groups: EntityGroup[];
}

export interface GraphNode {
  id: string;
  label: string;
  mentions: number;
  community: number;
  centrality: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface CrisisGraph {
  crisis_id: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  communities: string[][];
}
