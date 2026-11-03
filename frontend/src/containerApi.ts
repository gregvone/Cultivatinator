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
    ready: spawn ? "Ready for Spawning" : "Ready",
    used: "Used",
    failed: "Failed",
    completed: "Completed",
    depleted: "Depleted",
    active: "Active",
  })[stage || ""] ||
  stage ||
  "Not recorded";
