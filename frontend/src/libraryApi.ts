export type Kind =
  | "strains"
  | "lines"
  | "spores"
  | "physical"
  | "spawn"
  | "batches"
  | "fruiting";
export interface Photo {
  id: string;
  is_cover: boolean;
  url: string;
  thumbnail_url: string;
}
export interface LibraryRecord {
  id: string;
  kind: Kind;
  name: string | null;
  notes: string | null;
  status: "active" | "archived";
  created_at: string;
  stage?: string | null;
  batch_id?: string | null;
  batch_origin?: string | null;
  allocation_mode?: string | null;
  lifecycle?: string;
  remaining_quantity?: string | null;
  remaining_unit?: string | null;
  stock_item_id?: string | null;
  prepared_id?: string | null;
  balance_tracked?: boolean;
  strain_id: string | null;
  strain_name: string | null;
  strain_identification?: "known" | "mixed" | "partial" | "unknown" | null;
  contributing_strains?: { id: string; name: string }[];
  line_id: string | null;
  scientific_name: string | null;
  description: string | null;
  origin: string | null;
  supplier: string | null;
  supplier_reference: string | null;
  supplier_batch: string | null;
  acquisition_date: string | null;
  material_type: string | null;
  quantity: string | null;
  unit: string | null;
  storage_location: string | null;
  purchase_price: string | null;
  registration_batch: string | null;
  line_count: number;
  spore_count: number;
  physical_count: number;
  cover: Photo | null;
}
export interface Activity {
  id: number;
  occurred_at: string;
  event_type: string;
  description: string;
}
export class ApiError extends Error {
  fields: Record<string, string>;
  constructor(message: string, fields: Record<string, string> = {}) {
    super(message);
    this.fields = fields;
  }
}
export async function libraryApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
  base = "library",
): Promise<T> {
  const response = await fetch(`/api/${base}/${path}`, {
    method,
    headers:
      body instanceof FormData
        ? undefined
        : { "Content-Type": "application/json" },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const fields: Record<string, string> = {};
    if (Array.isArray(data.detail))
      for (const error of data.detail) fields[error.loc.at(-1)] = error.msg;
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : Object.values(fields).join("; ") ||
          `Request failed (${response.status})`,
      fields,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const cultureTypes = {
  lc_syringe: "Liquid culture syringe",
  lc_jar: "Liquid culture jar",
  agar_plate: "Agar plate",
  slant: "Culture slant",
  other_culture: "Other culture container",
};
export const sporeTypes = {
  spore_print: "Spore print",
  spore_syringe: "Spore syringe",
  spore_swab: "Spore swab",
  other_spore: "Other spore material",
};
export const origins = {
  purchased: "Purchased",
  gifted: "Gifted",
  other: "Other acquired source",
};
export const units = {
  mL: "mL",
  L: "L",
  g: "g",
  count: "Count",
  plate: "Plate",
  slant: "Slant",
  print: "Print",
  swab: "Swab",
};
export const kindNames: Record<Kind, string> = {
  strains: "Strains",
  lines: "Culture Lines",
  spores: "Spore Sources",
  physical: "Physical Cultures",
  spawn: "Spawn Jars & Bags",
  batches: "Grow Batches",
  fruiting: "Fruiting Containers",
};
export function title(record: LibraryRecord) {
  return record.name || record.id;
}
export function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Selection lists and related records must not disappear beyond the API page size.
export async function allLibraryRecords(
  path: string,
): Promise<LibraryRecord[]> {
  const [resource, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  params.set("limit", "1000");
  const records: LibraryRecord[] = [];
  for (let offset = 0; ; offset += 1000) {
    params.set("offset", String(offset));
    const page = await libraryApi<LibraryRecord[]>(`${resource}?${params}`);
    records.push(...page);
    if (page.length < 1000) return records;
  }
}

export function provenanceApi<T>(path: string, method = "GET", body?: unknown) {
  return libraryApi<T>(path, method, body, "provenance");
}
export const growTypes = {
  spawn_jar: "Colonized spawn jar",
  spawn_bag: "Colonized spawn bag",
  tray: "Tray",
  bag: "Fruiting bag",
  block: "Fruiting block",
  other: "Other fruiting container",
};
export interface Provenance {
  origin_type: string | null;
  origin_date: string | null;
  notes: string | null;
  revision: number;
  ancestry_status: "confirmed" | "uncertain" | "unknown";
  parents: { parent_id: string; confidence: "confirmed" | "possible" }[];
  relationships: { label: string; record: LibraryRecord }[];
  warnings: string[];
  allocation_mode: string | null;
  provenance_mode: string;
}
