export interface SourceFacts {
  fruiting_id: string;
  batch_id: string;
  spawn_ids: string[];
  line_ids: string[];
  ambiguous: boolean;
  fingerprint: string;
  suggestion?: {
    group_ids: string[];
    reason: string;
    automatic: boolean;
  } | null;
}
export interface Participant {
  id: number;
  fruiting_id: string;
  unit_id: string;
  group_id: string;
  group_name: string;
  unit_kind: string;
  plan_revision: number;
  classification: string;
  exposure_start: string;
  exposure_end: string | null;
  flush_count: number;
  sources: SourceFacts;
  evidence: {
    status: string;
    origin: string;
    review_reason?: string;
    treatment_start?: string;
    timing_precision?: string;
  };
}
export interface ParticipantPage {
  items: Participant[];
  total: number;
  candidates: SourceFacts[];
  candidate_total: number;
  revision: number;
  plan_revision: number;
  page: number;
  page_size: number;
  rules: {
    id: string;
    kind: string;
    source_id: string;
    group_id: string;
    plan_revision: number;
    active: number;
  }[];
  counts: {
    containers: number;
    treatment_units: number;
    known_spawn_sources: number;
    classification_counts: Record<string, number>;
  };
  classification_summary?: string;
  unit_warning: string;
}
