export interface RecordReference {
  record_id: string;
  title: string;
  target: string;
  stage?: string | null;
  archived?: boolean;
}
export interface AttentionItem extends RecordReference {
  alert_id: string;
  fingerprint: string;
  rule: string;
  category: string;
  recorded_date: string | null;
  elapsed_days: number | null;
  suppression?: { action: "dismiss" | "snooze"; until: string | null } | null;
  severity: "info" | "warning" | "critical";
  description: string;
}
export interface ActivityItem extends RecordReference {
  event_id: number;
  event_type: string;
  record_type: string;
  occurred_at: string;
  description: string;
}
export interface EnvironmentalObservation {
  record_id: string;
  area: string;
  observed_at: string;
  temperature_c: number | null;
  humidity_percent: number | null;
}
export interface DashboardSummary {
  counts: {
    active_cultures: number;
    spawn_containers: number;
    fruiting_units: number;
    open_alerts: number;
  };
  attention_total?: number;
  active_total?: number;
  stage_overview?: StageCount[];
  harvest_summary?: HarvestSummary | null;
  attention_items: AttentionItem[];
  active_cultivation: RecordReference[];
  recent_activity: ActivityItem[];
  environmental_observations: EnvironmentalObservation[];
}
export interface AppInfo {
  name: string;
  version: string;
  environment: string;
  storage: string;
}
export async function getApi<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Server returned HTTP ${response.status}.`);
  return response.json() as Promise<T>;
}

export interface StageCount {
  group: string;
  label: string;
  stage: string;
  count: number;
  target: string;
}
export interface HarvestSummary {
  start_date: string;
  end_date: string;
  timezone: string;
  harvest_count: number;
  wet_weight_count: number;
  wet_grams: string | null;
  fruiting_count: number;
}
export interface AttentionPage {
  items: AttentionItem[];
  total: number;
  page: number;
  page_size: number;
}
export interface ActivityPage extends Omit<AttentionPage, "items"> {
  items: ActivityItem[];
}
