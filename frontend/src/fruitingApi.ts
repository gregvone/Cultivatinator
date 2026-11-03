import { libraryApi } from "./libraryApi";
import type { LibraryRecord } from "./libraryApi";
export const fruitingApi = <T>(path: string, method = "GET", body?: unknown) =>
  libraryApi<T>(path, method, body, "fruiting");
export interface Environment {
  tent_name: string | null;
  temperature: string | null;
  temperature_unit: "C" | "F" | null;
  humidity: string | null;
  humidifier: string | null;
  fae: string | null;
  notes: string | null;
}
export interface Harvest {
  id: string;
  fruiting_id: string;
  flush_number: number;
  harvest_date: string;
  wet_grams: string | null;
  dry_grams: string | null;
  potency: number | null;
  potency_notes: string | null;
  notes: string | null;
  revision: number;
}
export interface Totals {
  harvest_count: number;
  wet_grams: string | null;
  dry_grams: string | null;
  wet_measured_count: number;
  dry_measured_count: number;
}
export interface FruitingDetail {
  record: LibraryRecord;
  source: LibraryRecord | null;
  legacy: boolean;
  run: {
    stage: string;
    current_flush: number;
    spawning_date: string | null;
    recipe_snapshot: {
      name: string;
      revision: number;
      ingredients: {
        name?: string;
        item_id?: string;
        quantity: string;
        unit: string;
      }[];
      instructions?: string;
      notes?: string;
    } | null;
    environment_snapshot: Environment | null;
    spawn_grams: string | null;
    substrate_grams: string | null;
    completed_date: string | null;
    failed_date: string | null;
    closing_notes: string | null;
  } | null;
  harvests: Harvest[];
  flushes: (Totals & {
    number: number;
    pinning_date: string | null;
    fruiting_date: string | null;
  })[];
  environment: Environment | null;
  environment_changes: {
    id: number;
    change_date: string;
    settings: Environment | null;
    notes: string;
  }[];
  results: Totals & {
    flushes_with_harvests: number;
    first_harvest_date: string | null;
    days_to_first_pinning: number | null;
    days_to_first_harvest: number | null;
    cycle_days: number | null;
  };
}
