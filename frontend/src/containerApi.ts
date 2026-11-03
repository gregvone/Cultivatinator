import type { LibraryRecord } from "./libraryApi";
import { useEffect, useState } from "react";
import { libraryApi } from "./libraryApi";
export const containerApi = <T>(path: string, method = "GET", body?: unknown) =>
  libraryApi<T>(path, method, body, "containers");
export interface LabelChoice {
  label?: string;
  new_label?: boolean;
  reusable?: boolean;
}
export interface AvailableLabels {
  available: string[];
  next_label: string;
  reusable: boolean;
}
export function useAvailableLabels(material: string, reusable?: boolean) {
  const [data, setData] = useState<AvailableLabels | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    containerApi<AvailableLabels>(
      `available?material_type=${encodeURIComponent(material)}${reusable == null ? "" : `&reusable=${reusable}`}`,
    )
      .then((v) => {
        if (!Array.isArray(v.available) || typeof v.next_label !== "string")
          throw new Error(
            "Available labels could not be loaded; automatic allocation remains available.",
          );
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [material, reusable, revision]);
  return { data, error, reload: () => setRevision((v) => v + 1) };
}
export const phaseName = (stage?: string | null, spawn = false) =>
  ({
    colonizing: "Colonizing",
    unrecorded: "Stage not recorded",
    pinning: "Pinning",
    fruiting: "Fruiting",
    harvest: "Harvest",
    ready: spawn ? "Ready for Spawning" : "Ready",
    used: "Used",
    failed: "Failed",
    completed: "Completed",
    depleted: "Depleted",
    active: "Active",
  })[stage || ""] ||
  stage ||
  "Not recorded";

// Record visibility is administrative; it never establishes agar readiness.
export type CultivationRecord = Partial<
  Pick<
    LibraryRecord,
    | "material_type"
    | "growth_stage"
    | "lifecycle"
    | "stage"
    | "status"
    | "fruiting_stage"
  >
> & { kind?: string };
export function cultivationStatus(record: CultivationRecord) {
  if (record.fruiting_stage) return phaseName(record.fruiting_stage);
  const terminal = ["used", "failed", "completed", "depleted"].find(
    (stage) =>
      record.lifecycle === stage ||
      record.growth_stage === stage ||
      record.stage === stage,
  );
  if (terminal) return phaseName(terminal);
  if (record.kind === "fruiting" && (!record.stage || record.stage === "ready"))
    return "Stage not recorded";
  if (record.kind === "fruiting" && record.stage === "finished")
    return "Completed";
  if (record.material_type === "agar_plate") {
    if (record.growth_stage === "ready") return "Ready";
    if (record.growth_stage === "colonizing") return "Germinating";
    return "Readiness not recorded";
  }
  return phaseName(
    record.growth_stage || record.stage || record.lifecycle || record.status,
    record.kind === "spawn",
  );
}
