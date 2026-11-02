export interface RecordReference {
  record_id: string;
  title: string;
  target: string;
}
export interface AttentionItem extends RecordReference {
  severity: "info" | "warning" | "critical";
  description: string;
}
export interface ActivityItem extends RecordReference {
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
