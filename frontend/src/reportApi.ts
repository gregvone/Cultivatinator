import { localToday } from "./libraryApi";
export type GroupBy = "strain" | "line" | "recipe";
export const groupNames: Record<GroupBy, string> = {
  strain: "Strain",
  line: "Genetic culture line",
  recipe: "Substrate recipe",
};
export interface Average {
  value: string | null;
  sample_count: number;
  missing_count: number;
}
export interface ReportStats {
  completed: number;
  failed: number;
  terminal_count: number;
  failure_rate_percent: string | null;
  qualifying_containers: number;
  excluded_incomplete_wet: number;
  average_wet_grams: string | null;
  qualifying_wet_total_grams: string | null;
  total_known_wet_grams: string | null;
  completed_known_wet_grams: string | null;
  failed_known_wet_grams: string | null;
  wet_measured_containers: number;
  wet_measurement_count: number;
  harvest_count: number;
  distinct_spawn_sources: number;
  containers_without_known_spawn: number;
  average_dry_grams: Average;
  days_to_first_pinning: Average;
  days_to_first_harvest: Average;
  cycle_days: Average;
}
export interface ReportRecord {
  id: string;
  label: string | null;
  name: string | null;
  outcome: "completed" | "failed" | "active";
  outcome_date: string | null;
  archived: boolean;
  legacy: boolean;
  strain_identity: string;
  line_identity: string;
  strain_ids: string[];
  line_ids: string[];
  strain_names: string[];
  line_names: string[];
  spawn_ids: string[];
  species: string | null;
  recipe_id: string | null;
  recipe_name: string | null;
  recipe_revision: number | null;
  harvest_count: number;
  wet_measurement_count: number;
  known_wet_grams: string | null;
  complete_wet: boolean;
  known_dry_grams: string | null;
  complete_dry: boolean;
  days_to_first_pinning: number | null;
  days_to_first_harvest: number | null;
  cycle_days: number | null;
}
export interface ReportGroup {
  key: string;
  name: string;
  identity: string;
  ranked: boolean;
  preliminary: boolean;
  stats: ReportStats;
  record_ids: string[];
  revisions: {
    revision: number | null;
    name: string;
    snapshot: {
      ingredients?: {
        name?: string;
        item_id?: string;
        quantity: string;
        unit: string;
      }[];
      instructions?: string;
      notes?: string;
    };
    stats: ReportStats;
    record_ids: string[];
  }[];
}
export interface FlushResult {
  number: number;
  containers_reached: number;
  qualifying_containers: number;
  excluded_incomplete_wet: number;
  average_wet_grams: string | null;
  total_known_wet_grams: string | null;
  record_ids: string[];
  qualifying_record_ids: string[];
}
export interface PerformanceReport {
  group_by: GroupBy;
  period: { label: string; start_date: string | null; end_date: string | null };
  options: {
    strains: { id: string; name: string; scientific_name: string | null }[];
    species: string[];
  };
  summary: ReportStats;
  groups: ReportGroup[];
  flushes: FlushResult[];
  records: ReportRecord[];
  active_records: ReportRecord[];
  matching_containers: number;
  terminal_containers_outside_period: number;
  undated_terminal_excluded: number;
  legacy_containers: number;
}
export const measure = (value: string | null, unit = "g") =>
  value == null
    ? "Unknown"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(Number(value))}${unit ? ` ${unit}` : ""}`;
export function periodBounds(
  range: string,
  start: string,
  end: string,
  today = localToday(),
) {
  if (range === "all") return {};
  if (range === "custom") return { start_date: start, end_date: end };
  const from = new Date(`${today}T12:00:00`);
  from.setDate(from.getDate() - (range === "30" ? 29 : 89));
  const local = `${from.getFullYear()}-${String(from.getMonth() + 1).padStart(2, "0")}-${String(from.getDate()).padStart(2, "0")}`;
  return { start_date: local, end_date: today };
}
