import type { Photo } from "./libraryApi";
export interface GeneticNode {
  id: string;
  name: string;
  strain_id: string | null;
  status: string;
  origin_type: string;
  source: { kind: string; id: string } | null;
  photo: Photo | null;
  photo_source: string;
  photos: (Photo & { owner_id: string; line_cover: boolean })[];
  fruiting_sources: { id: string; name: string; kind: string }[];
  can_isolate: boolean;
}
export interface GeneticGraph {
  strains: { id: string; name: string; status: string; cover: Photo | null }[];
  nodes: GeneticNode[];
  edges: { parent_id: string; line_id: string; confidence: string }[];
}
export const originNames: Record<string, string> = {
  external: "Acquired",
  isolate: "Selected isolate",
  clone: "Tissue clone",
  spores: "Spore-derived",
  other: "Other origin",
  unknown: "Unknown origin",
};
export function layoutGraph(
  data: GeneticGraph,
  family: string,
  kingdom: boolean,
  collapsed: Set<string>,
) {
  const members = data.nodes.filter(
      (n) => kingdom || (n.strain_id || "unknown") === family,
    ),
    ids = new Set(members.map((n) => n.id)),
    hidden = new Set<string>();
  const incoming = new Map<string, GeneticGraph["edges"]>();
  for (const e of data.edges) {
    const a = incoming.get(e.line_id) || [];
    a.push(e);
    incoming.set(e.line_id, a);
  }
  for (let pass = 0; pass < members.length; pass++) {
    let changed = false;
    for (const n of members) {
      const parents = (incoming.get(n.id) || []).filter((e) =>
        ids.has(e.parent_id),
      );
      if (
        parents.length &&
        parents.every(
          (e) => hidden.has(e.parent_id) || collapsed.has(e.parent_id),
        ) &&
        !hidden.has(n.id)
      ) {
        hidden.add(n.id);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const visible = members.filter((n) => !hidden.has(n.id)),
    positions = new Map<string, { x: number; y: number }>(),
    groups = kingdom ? [...data.strains.map((s) => s.id), "unknown"] : [family];
  let offset = 30,
    height = 400;
  const headers: { id: string; x: number; width: number }[] = [];
  for (const group of groups) {
    const nodes = visible.filter((n) => (n.strain_id || "unknown") === group),
      levels = new Map(nodes.map((n) => [n.id, 0]));
    for (let pass = 0; pass < nodes.length; pass++) {
      let changed = false;
      for (const e of data.edges)
        if (levels.has(e.parent_id) && levels.has(e.line_id)) {
          const next = Math.min(
            nodes.length,
            (levels.get(e.parent_id) || 0) + 1,
          );
          if (next > (levels.get(e.line_id) || 0)) {
            levels.set(e.line_id, next);
            changed = true;
          }
        }
      if (!changed) break;
    }
    const rows = new Map<number, number>();
    for (const n of nodes) {
      const depth = levels.get(n.id) || 0,
        col = rows.get(depth) || 0;
      rows.set(depth, col + 1);
      positions.set(n.id, { x: offset + col * 240, y: 120 + depth * 280 });
      height = Math.max(height, 390 + depth * 280);
    }
    const width = Math.max(240, ...[...rows.values()].map((c) => c * 240));
    headers.push({ id: group, x: offset, width });
    offset += width + 70;
  }
  return { nodes: visible, positions, headers, width: offset, height };
}
