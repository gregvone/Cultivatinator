import { phaseName } from "./containerApi";
import {
  CircleDot,
  Syringe,
  FlaskConical,
  Container,
  Fingerprint,
  Sprout,
} from "lucide-react";
import type { LibraryRecord } from "./libraryApi";
import { cultureTypes, sporeTypes, growTypes } from "./libraryApi";

const agar = ["agar_plate", "slant"];
const liquid = ["lc_jar", "lc_syringe"];
export const quickCreate = [
  {
    id: "agar-plate",
    title: "New Agar Plate",
    icon: CircleDot,
    kinds: ["physical", "spores"],
    physical: [...agar, ...liquid],
    description:
      "Start from an existing agar culture, liquid culture, or spore source.",
    deferred: null,
  },
  {
    id: "lc-syringe",
    title: "New LC Syringe",
    icon: Syringe,
    kinds: ["physical"],
    physical: liquid,
    description:
      "Select an existing liquid culture, preferably an LC container or jar.",
    deferred: null,
  },
  {
    id: "lc-container",
    title: "New LC Container / Jar",
    icon: FlaskConical,
    kinds: ["physical"],
    physical: [...agar, ...liquid],
    description: "Select an existing agar or liquid culture source.",
    deferred: null,
  },
  {
    id: "spawn",
    title: "New Spawn Jar / Bag",
    icon: Container,
    kinds: ["physical"],
    physical: [...agar, ...liquid],
    description:
      "Create inoculated spawn from an existing agar or liquid culture.",
    deferred: null,
  },
  {
    id: "spore-print",
    title: "New Spore Print",
    icon: Fingerprint,
    kinds: ["fruiting"],
    physical: [],
    description:
      "Register a spore print already collected from a tracked fruiting container.",
    deferred: null,
  },
  {
    id: "fruiting-container",
    title: "New Fruiting Container",
    icon: Sprout,
    kinds: ["spawn"],
    physical: [],
    description:
      "Select a Ready spawn jar or bag for a future spawning operation.",
    deferred:
      "Actual spawning, substrate allocation, and spawn consumption will be available in Milestone 2C.3. No fruiting container is created and no spawn is marked Used here.",
  },
] as const;
export type QuickOperation = (typeof quickCreate)[number];
export function eligibleSource(
  operation: QuickOperation,
  record: LibraryRecord,
) {
  if (
    ["used", "depleted", "completed", "failed"].includes(
      record.lifecycle || "active",
    ) ||
    (record.balance_tracked &&
      record.remaining_quantity != null &&
      /^0*(\.0*)?$/.test(record.remaining_quantity)) ||
    record.status !== "active" ||
    !(operation.kinds as readonly string[]).includes(record.kind)
  )
    return false;
  if (
    record.kind === "physical" &&
    record.material_type === "agar_plate" &&
    record.growth_stage !== "ready"
  )
    return false;
  if (record.kind === "physical")
    return (operation.physical as readonly string[]).includes(
      record.material_type ?? "",
    );
  if (record.kind === "spores")
    return record.material_type != null && record.material_type in sporeTypes;
  if (record.kind === "spawn")
    return (
      record.stage === "ready" &&
      ["spawn_jar", "spawn_bag"].includes(record.material_type ?? "")
    );
  return record.kind === "fruiting";
}
export function workflowPath(
  operation: QuickOperation,
  source?: LibraryRecord,
) {
  const params = source
    ? `?${new URLSearchParams({ source_kind: source.kind, source_id: source.id })}`
    : "";
  return `/quick-create/${operation.id}${params}`;
}
export function sourceLabel(record: LibraryRecord) {
  const names = record.contributing_strains?.map((s) => s.name);
  const strain = names?.length
    ? `${names.length > 1 ? "Mixed Strains: " : ""}${names.join(", ")}${record.strain_identification === "partial" ? " (partial; unknown sources)" : ""}`
    : record.strain_name || "Unknown strain";
  const material =
    (
      { ...cultureTypes, ...sporeTypes, ...growTypes } as Record<string, string>
    )[record.material_type ?? ""] || "Fruiting container";
  return `${record.physical_label || record.id}${record.physical_label ? ` (record ${record.id})` : ""}${record.name ? ` · ${record.name}` : ""} · ${material} · ${strain}${record.line_id ? ` · Line ${record.line_id}` : ""} · ${phaseName(record.growth_stage || record.stage || record.status, record.kind === "spawn")}`;
}
export function availableOperations(record: LibraryRecord) {
  return quickCreate.filter((op) => eligibleSource(op, record));
}
// A record ID is always paired with its kind; never infer a genetic source from a strain.
export function sourceKey(record: Pick<LibraryRecord, "kind" | "id">) {
  return `${record.kind}:${record.id}`;
}
