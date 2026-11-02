import { useEffect, useRef, useState } from "react";
import { libraryApi } from "./libraryApi";
export const preparationApi = <T>(
  path: string,
  method = "GET",
  body?: unknown,
) => libraryApi<T>(path, method, body, "preparation");
export interface Stock {
  id: string;
  name: string;
  category: string;
  unit: string;
  available: string | null;
  container_type: string | null;
  physical_id: string | null;
  spore_id: string | null;
  revision: number;
  notes: string | null;
  storage_location?: string | null;
  status: string;
}
export interface Ingredient {
  item_id: string;
  quantity: string;
  unit: string;
  name?: string;
}
export interface Processing {
  method: string | null;
  duration_minutes: number | null;
  temperature_c: string | null;
  pressure_psi: string | null;
  notes: string | null;
}
export interface Recipe {
  id: string;
  name: string;
  recipe_type: string;
  batch_yield: number;
  ingredients: Ingredient[];
  instructions: string | null;
  processing: Processing;
  shelf_life_days: number | null;
  revision: number;
  status: string;
}
export interface Prepared {
  id: string;
  batch_id: string;
  material_type: string;
  stage: string;
  use_by: string | null;
  expired: boolean;
  physical_id: string | null;
  spawn_id: string | null;
  source: {
    kind: "physical" | "spores";
    id: string;
    operation_id: string;
    date: string | null;
    usage_quantity: string | null;
    unit: string;
  } | null;
  snapshot: {
    ingredients: Ingredient[];
    recipe: Omit<Recipe, "id" | "revision" | "status"> | null;
    recipe_revision?: number | null;
    processing: Processing;
    preparation_date: string | null;
    notes: string | null;
    container_name: string;
  };
}
export interface Ledger {
  id: number;
  operation_id: string;
  item_id: string;
  entry_type: string;
  amount: string | null;
  unit: string;
  before_quantity: string | null;
  after_quantity: string | null;
  reason: string;
  created_at: string;
}
export const materialNames: Record<string, string> = {
  agar_plate: "Agar plate",
  lc_jar: "LC container / jar",
  lc_syringe: "LC syringe",
  spawn_jar: "Spawn jar",
  spawn_bag: "Spawn bag",
  fruiting_tray: "Fruiting tray",
};
export const stockUnits = {
  mg: "Milligrams (mg)",
  g: "Grams (g)",
  kg: "Kilograms (kg)",
  oz: "Ounces — weight (oz)",
  lb: "Pounds (lb)",
  mL: "Milliliters (mL)",
  L: "Liters (L)",
  us_fl_oz: "US fluid ounces (volume)",
  us_cup: "US cups (volume)",
  count: "Each / count",
  each: "Each",
  plate: "Plate",
  print: "Print",
  swab: "Swab",
  slant: "Slant",
};
export const stageName = (value: string) =>
  ({
    preparing: "Preparing",
    ready: "Ready to Inoculate",
    inoculated: "Inoculated",
    completed: "Completed",
    failed: "Failed",
  })[value] || value;
export function newRequestKey(random: Crypto = crypto) {
  if (typeof random.randomUUID === "function") return random.randomUUID();
  // getRandomValues also works on private-network HTTP origins, where
  // randomUUID is unavailable. Preserve random retry keys without requiring HTTPS.
  return Array.from(random.getRandomValues(new Uint8Array(16)), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}
export function useInventoryCommand() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const prior = useRef<{ signature: string; key: string } | null>(null);
  async function send<T>(
    path: string,
    payload: unknown,
    method = "POST",
  ): Promise<T | undefined> {
    const signature = JSON.stringify([path, method, payload]);
    if (prior.current?.signature !== signature)
      prior.current = { signature, key: newRequestKey() };
    setBusy(true);
    setError("");
    try {
      return await preparationApi<T>(path, method, {
        ...(payload as object),
        request_key: prior.current!.key,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save operation");
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, send };
}
export function useInventoryList<T>(path: string) {
  const [data, setData] = useState<T[] | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setError("");
    preparationApi<T[]>(path)
      .then((v) => {
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [path, revision]);
  return { data, error, reload: () => setRevision((v) => v + 1) };
}
// Preview arithmetic uses integer thousandths, never floating-point balances.
export function scaleQuantity(
  value: string,
  numerator: number,
  denominator = 1,
): string {
  if (
    !/^\d+(\.\d{0,3})?$/.test(value) ||
    !Number.isInteger(numerator) ||
    numerator < 0 ||
    !Number.isInteger(denominator) ||
    denominator < 1
  )
    return "";
  const [whole, fraction = ""] = value.split(".");
  const milli = BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, "0"));
  const result =
    (milli * BigInt(numerator) * 2n + BigInt(denominator)) /
    (2n * BigInt(denominator));
  return `${result / 1000n}.${String(result % 1000n).padStart(3, "0")}`;
}

export function compatibleUnits(unit: string) {
  const dimensions = [
    ["mg", "g", "kg", "oz", "lb"],
    ["mL", "L", "us_fl_oz", "us_cup"],
    ["count", "each"],
  ];
  const group = dimensions.find((g) => g.includes(unit)) || [unit];
  return Object.fromEntries(
    Object.entries(stockUnits).filter(([u]) => group.includes(u)),
  );
}
export interface Pool {
  item_id: string;
  name: string;
  available: string;
  ready: number;
  inoculated: number;
  preparing: number;
  other_reserved: number;
  reserved: number;
  total: string;
}
