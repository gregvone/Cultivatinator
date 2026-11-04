import { useEffect, useState } from "react";
import { libraryApi } from "./libraryApi";
export const environmentApi = <T>(
  path: string,
  method = "GET",
  body?: unknown,
) => libraryApi<T>(path, method, body, "environment");
export type Metric = "temperature_f" | "humidity" | "co2";
export const metrics: {
  key: Metric;
  label: string;
  unit: string;
  min: number;
  max: number;
}[] = [
  {
    key: "temperature_f",
    label: "Temperature",
    unit: "°F",
    min: -148,
    max: 212,
  },
  {
    key: "humidity",
    label: "Relative humidity",
    unit: "% RH",
    min: 0,
    max: 100,
  },
  { key: "co2", label: "CO₂", unit: "ppm", min: 0, max: 1000000 },
];
export interface Profile {
  id: string;
  name: string;
  species: string | null;
  notes: string | null;
  status: string;
  revision: number;
  targets: Record<string, number | null>;
}
export interface Tent {
  id: string;
  name: string;
  description: string | null;
  status: string;
  revision: number;
  profile_id: string | null;
}
export interface Reading {
  id: number;
  tent_id: string;
  observed_at: string;
  created_at: string;
  temperature_f: number;
  humidity: number;
  co2: number | null;
  humidifier: number | null;
  fan: number | null;
  notes: string | null;
  source: string;
  snapshot: Profile;
  evaluations: Partial<Record<Metric, string>>;
  replaces_id: number | null;
  correction_reason: string | null;
  superseded_by: number | null;
  fruiting_ids: string[];
}
export interface Occupancy {
  id: number;
  tent_id: string;
  tent_name: string;
  fruiting_id: string;
  entered_at: string;
  left_at: string | null;
  revision: number;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Warning {
  metric: Metric;
  state: string;
  value: number;
  unit: string;
  observed_at: string;
  reading_id: number;
}
export interface Overview {
  tent: Tent;
  profile: Profile | null;
  latest: Record<Metric, { value: number; observed_at: string } | null>;
  warnings: Warning[];
  occupancy_count: number;
}
export function useEnvironment<T>(path: string, revision = 0) {
  const [state, setState] = useState<{
    data: T | null;
    error: string;
    loading: boolean;
  }>({ data: null, error: "", loading: true });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ data: null, error: "", loading: true });
    environmentApi<T>(path)
      .then((data) => {
        if (active) setState({ data, error: "", loading: false });
      })
      .catch((e) => {
        if (active)
          setState({ data: null, error: String(e.message), loading: false });
      });
    return () => {
      active = false;
    };
  }, [path, revision, retry]);
  return { ...state, retry: () => setRetry((x) => x + 1) };
}
export function localDateTime(value = new Date().toISOString()) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 23);
}
export function observationTime(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()))
    throw new Error("Enter a valid local date and time");
  // Reject browser normalization of nonexistent DST wall-clock times.
  if (!localDateTime(date.toISOString()).startsWith(value))
    throw new Error(
      "This local time does not exist due to a daylight-saving change",
    );
  return date.toISOString();
}
export const friendlyTime = (value: string) => new Date(value).toLocaleString();
