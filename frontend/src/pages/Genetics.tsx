import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Dna } from "lucide-react";
import { useApi } from "../useApi";
import { libraryApi } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import { PageHeader } from "../components/UI";
import { LineagePanel } from "./Provenance";
import { layoutGraph, originNames } from "../genetics";
import type { GeneticGraph, GeneticNode } from "../genetics";
function Picture({
  node,
}: {
  node: Pick<GeneticNode, "photo" | "photo_source" | "name">;
}) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [node.photo?.id]);
  return node.photo && !broken ? (
    <img
      src={node.photo.thumbnail_url}
      alt={`${node.name} — ${node.photo_source}`}
      onError={() => setBroken(true)}
      draggable={false}
    />
  ) : (
    <Dna aria-label="No photograph" />
  );
}
export default function Genetics() {
  const { data, error, retry } = useApi<GeneticGraph>("genetics", true),
    [params, setParams] = useSearchParams();
  const kingdom = params.get("view") === "kingdom",
    family = params.get("strain") || data?.strains[0]?.id || "unknown",
    selected = data?.nodes.find((n) => n.id === params.get("node"));
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set()),
    [query, setQuery] = useState(""),
    [camera, setCamera] = useState({ x: 30, y: 20, z: 1 }),
    [actionError, setActionError] = useState(""),
    [workflow, setWorkflow] = useState<LibraryRecord | null>(null),
    [source, setSource] = useState(""),
    [pendingFocus, setPendingFocus] = useState<string | null>(null);
  const canvas = useRef<HTMLDivElement>(null),
    pointers = useRef(new Map<number, { x: number; y: number }>());
  const graph = useMemo(
    () => (data ? layoutGraph(data, family, kingdom, collapsed) : null),
    [data, family, kingdom, collapsed],
  );
  const update = (values: Record<string, string>) =>
    setParams((p) => {
      for (const [k, v] of Object.entries(values)) p.set(k, v);
      return p;
    });
  function fit() {
    if (!graph) return;
    const w = canvas.current?.clientWidth || 900,
      h = canvas.current?.clientHeight || 650,
      z = Math.min(
        1.3,
        Math.max(0.005, Math.min(w / graph.width, h / graph.height) * 0.9),
      );
    setCamera({
      x: (w - graph.width * z) / 2,
      y: (h - graph.height * z) / 2,
      z,
    });
  }
  useEffect(() => {
    fit();
  }, [family, kingdom, !!data]);
  useEffect(() => {
    setWorkflow(null);
    setSource("");
    setActionError("");
  }, [selected?.id]);
  useEffect(() => {
    window.addEventListener("focus", retry);
    return () => window.removeEventListener("focus", retry);
  }, [retry]);
  function center(id: string) {
    setCollapsed(new Set());
    update({ node: id });
    if (!data) return;
    const pos = layoutGraph(data, family, kingdom, new Set()).positions.get(id);
    if (pos)
      setCamera({
        z: 1,
        x: (canvas.current?.clientWidth || 900) / 2 - pos.x - 100,
        y: (canvas.current?.clientHeight || 650) / 2 - pos.y - 100,
      });
  }
  function focus(n: GeneticNode) {
    setCollapsed(new Set());
    setPendingFocus(n.id);
    update({ view: "family", strain: n.strain_id || "unknown", node: n.id });
  }
  useEffect(() => {
    if (!pendingFocus || !graph) return;
    const pos = graph.positions.get(pendingFocus);
    if (pos) {
      setCamera({
        z: 1,
        x: (canvas.current?.clientWidth || 900) / 2 - pos.x - 100,
        y: (canvas.current?.clientHeight || 650) / 2 - pos.y - 100,
      });
      setPendingFocus(null);
    }
  }, [graph, pendingFocus]);
  function zoom(factor: number, cx?: number, cy?: number) {
    const r = canvas.current?.getBoundingClientRect(),
      x = cx === undefined ? (r?.width || 900) / 2 : cx - (r?.left || 0),
      y = cy === undefined ? (r?.height || 650) / 2 : cy - (r?.top || 0);
    setCamera((c) => {
      const z = Math.max(0.005, Math.min(2, c.z * factor));
      return { z, x: x - ((x - c.x) * z) / c.z, y: y - ((y - c.y) * z) / c.z };
    });
  }
  async function launch(kind: string, id: string) {
    setActionError("");
    try {
      setWorkflow(await libraryApi<LibraryRecord>(`${kind}/${id}`));
    } catch (e) {
      setActionError(String(e));
    }
  }
  async function choose(photo_id: string | null) {
    if (!selected) return;
    try {
      await libraryApi(
        `lines/${selected.id}/photo`,
        "PUT",
        { photo_id },
        "genetics",
      );
      retry();
    } catch (e) {
      setActionError(String(e));
    }
  }
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      zoom(e.deltaY < 0 ? 1.1 : 0.9, e.clientX, e.clientY);
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [!!data]);
  const aggregate = kingdom && camera.z < 0.35;
  const results =
    data?.nodes
      .filter((n) =>
        `${n.name} ${n.id}`.toLowerCase().includes(query.toLowerCase()),
      )
      .slice(0, 25) || [];
  const parents = (id: string) =>
      data?.edges.filter((e) => e.line_id === id) || [],
    children = (id: string) =>
      data?.edges.filter((e) => e.parent_id === id) || [];
  return (
    <>
      <PageHeader
        title="Genetics"
        description="Explore recorded origins. Every branch tells a documented story."
      />
      <div className="genetics-controls panel">
        <div className="actions" aria-label="Genetics view">
          <button
            aria-pressed={!kingdom}
            onClick={() => update({ view: "family" })}
          >
            Strain Family
          </button>
          <button
            aria-pressed={kingdom}
            onClick={() => update({ view: "kingdom" })}
          >
            Magic Kingdom
          </button>
          <label>
            Strain{" "}
            <select
              aria-label="Strain"
              value={family}
              onChange={(e) => {
                setCollapsed(new Set());
                update({ strain: e.target.value, view: "family" });
              }}
            >
              {data?.strains.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.status === "archived" ? " · Archived" : ""}
                </option>
              ))}
              <option value="unknown">Unknown Strain</option>
            </select>
          </label>
          <label>
            Search cultures{" "}
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name or permanent ID"
            />
          </label>
        </div>
        {query && (
          <ul className="genetic-results">
            {results.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => {
                    if (!kingdom && (n.strain_id || "unknown") !== family)
                      focus(n);
                    else center(n.id);
                    setQuery("");
                  }}
                >
                  {n.name} · {n.id} · {n.status}
                </button>
              </li>
            ))}
            {!results.length && <li>No matching cultures</li>}
          </ul>
        )}
      </div>
      {error && (
        <div role="alert">
          {error}
          <button onClick={retry}>Retry genetics</button>
        </div>
      )}
      {!data && !error && <p role="status">Loading genetic families…</p>}
      {data && graph && (
        <div className="genetics-workspace">
          <section
            className="panel genetic-stage"
            aria-label={kingdom ? "Magic Kingdom" : "Strain Family"}
          >
            <div className="actions genetic-toolbar">
              <button onClick={() => zoom(1.25)}>Zoom In</button>
              <button onClick={() => zoom(0.8)}>Zoom Out</button>
              <button onClick={fit}>Fit to Screen</button>
              <button onClick={() => setCamera({ x: 30, y: 20, z: 1 })}>
                Reset View
              </button>
              <button onClick={() => setCollapsed(new Set())}>
                Expand All
              </button>
              <span>{Math.round(camera.z * 100)}%</span>
            </div>
            <p className="genetic-legend">
              Solid: confirmed parent · Dashed: possible parent · Strain
              headings are groups, never parents. Drag to pan; two fingers to
              pan/zoom.
            </p>
            {!graph.nodes.length && (
              <p className="empty-state">
                No culture lines in this family. Receive a culture or establish
                one from an existing source.
              </p>
            )}
            <div
              className="genetic-canvas"
              ref={canvas}
              tabIndex={0}
              aria-label="Family tree canvas. Arrow keys pan; plus and minus zoom. Tab selects cultures."
              onKeyDown={(e) => {
                if (e.target !== e.currentTarget) return;
                if (
                  [
                    "ArrowLeft",
                    "ArrowRight",
                    "ArrowUp",
                    "ArrowDown",
                    "+",
                    "-",
                  ].includes(e.key)
                )
                  e.preventDefault();
                if (e.key === "+") zoom(1.25);
                if (e.key === "-") zoom(0.8);
                setCamera((c) => ({
                  ...c,
                  x:
                    c.x +
                    (e.key === "ArrowLeft"
                      ? 50
                      : e.key === "ArrowRight"
                        ? -50
                        : 0),
                  y:
                    c.y +
                    (e.key === "ArrowUp"
                      ? 50
                      : e.key === "ArrowDown"
                        ? -50
                        : 0),
                }));
              }}
              onPointerDown={(e) => {
                if ((e.target as Element).closest("button")) return;
                e.currentTarget.setPointerCapture(e.pointerId);
                pointers.current.set(e.pointerId, {
                  x: e.clientX,
                  y: e.clientY,
                });
              }}
              onPointerMove={(e) => {
                const old = pointers.current.get(e.pointerId);
                if (!old) return;
                const other = [...pointers.current.entries()].find(
                  ([id]) => id !== e.pointerId,
                )?.[1];
                if (other) {
                  const a = Math.hypot(old.x - other.x, old.y - other.y),
                    b = Math.hypot(e.clientX - other.x, e.clientY - other.y);
                  if (a)
                    zoom(
                      b / a,
                      (e.clientX + other.x) / 2,
                      (e.clientY + other.y) / 2,
                    );
                } else
                  setCamera((c) => ({
                    ...c,
                    x: c.x + e.clientX - old.x,
                    y: c.y + e.clientY - old.y,
                  }));
                pointers.current.set(e.pointerId, {
                  x: e.clientX,
                  y: e.clientY,
                });
              }}
              onPointerUp={(e) => pointers.current.delete(e.pointerId)}
              onPointerCancel={(e) => pointers.current.delete(e.pointerId)}
            >
              {aggregate && (
                <div className="genetic-overview" aria-label="Family overview">
                  {graph.headers.map((g) => {
                    const strain = data.strains.find((s) => s.id === g.id);
                    return (
                      <article key={g.id}>
                        <Picture
                          node={{
                            name: strain?.name || "Unknown Strain",
                            photo: strain?.cover || null,
                            photo_source: "strain cover",
                          }}
                        />
                        <h2>{strain?.name || "Unknown Strain"}</h2>
                        <p>
                          {
                            data.nodes.filter(
                              (n) => (n.strain_id || "unknown") === g.id,
                            ).length
                          }{" "}
                          culture lines
                        </p>
                        <button
                          onClick={() => {
                            setCollapsed(new Set());
                            update({ view: "family", strain: g.id });
                          }}
                        >
                          Focus on This Family
                        </button>
                      </article>
                    );
                  })}
                </div>
              )}
              <div
                className={`genetic-world ${camera.z >= 0.8 ? "close" : camera.z >= 0.4 ? "medium" : "far"}`}
                style={{
                  width: graph.width,
                  height: graph.height,
                  transform: `translate(${camera.x}px,${camera.y}px) scale(${camera.z})`,
                }}
              >
                <svg
                  className="genetic-edges"
                  width={graph.width}
                  height={graph.height}
                  aria-hidden="true"
                >
                  {!aggregate &&
                    data.edges.map((e) => {
                      const a = graph.positions.get(e.parent_id),
                        b = graph.positions.get(e.line_id);
                      return a && b ? (
                        <path
                          key={`${e.parent_id}/${e.line_id}`}
                          d={`M${a.x + 100},${a.y + (camera.z >= 0.8 ? 205 : camera.z >= 0.4 ? 180 : 120)} C${a.x + 100},${a.y + 245} ${b.x + 100},${b.y - 40} ${b.x + 100},${b.y}`}
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeDasharray={
                            e.confidence === "possible" ? "8 6" : undefined
                          }
                        />
                      ) : null;
                    })}
                </svg>
                {!aggregate &&
                  graph.headers.map((g) => {
                    const s = data.strains.find((s) => s.id === g.id);
                    return (
                      <div
                        key={g.id}
                        className="genetic-family"
                        style={{
                          left: g.x,
                          width: g.width,
                        }}
                      >
                        {s?.cover ? (
                          <img
                            src={s.cover.thumbnail_url}
                            alt={`${s.name} strain cover`}
                          />
                        ) : (
                          <Dna />
                        )}
                        <strong>{s?.name || "Unknown Strain"}</strong>
                        <small>
                          {
                            data.nodes.filter(
                              (n) => (n.strain_id || "unknown") === g.id,
                            ).length
                          }{" "}
                          culture lines
                        </small>
                      </div>
                    );
                  })}
                {!aggregate &&
                  graph.nodes.map((n) => {
                    const pos = graph.positions.get(n.id)!;
                    return (
                      <div
                        key={n.id}
                        className={`genetic-node ${selected?.id === n.id ? "selected" : ""} ${n.status === "archived" ? "archived" : ""}`}
                        style={{ left: pos.x, top: pos.y }}
                      >
                        <button
                          className="genetic-select"
                          aria-pressed={selected?.id === n.id}
                          onClick={() => update({ node: n.id })}
                          aria-label={`${n.name} · ${n.id} · ${originNames[n.origin_type]} · ${n.status} · ${
                            parents(n.id).length
                              ? parents(n.id)
                                  .map(
                                    (p) =>
                                      p.confidence + " parent " + p.parent_id,
                                  )
                                  .join(", ")
                              : "Unknown ancestry"
                          }`}
                        >
                          <Picture node={n} />
                          <strong>{n.name}</strong>
                          <small>{n.id}</small>
                          <span className="genetic-origin">
                            {originNames[n.origin_type]}
                          </span>
                          <span className="genetic-extra">
                            {n.status === "archived" ? "Archived" : "Active"} ·{" "}
                            {parents(n.id).length
                              ? parents(n.id).some(
                                  (p) => p.confidence === "possible",
                                )
                                ? "Possible ancestry"
                                : "Confirmed parent"
                              : "Unknown ancestry"}
                            <br />
                            {n.photo_source === "strain cover"
                              ? "Strain cover fallback"
                              : ""}
                          </span>
                        </button>
                        {children(n.id).length > 0 && (
                          <button
                            className="genetic-collapse"
                            aria-expanded={!collapsed.has(n.id)}
                            onClick={() =>
                              setCollapsed((old) => {
                                const next = new Set(old);
                                if (next.has(n.id)) next.delete(n.id);
                                else next.add(n.id);
                                return next;
                              })
                            }
                          >
                            {collapsed.has(n.id) ? "Expand" : "Collapse"}{" "}
                            descendants
                          </button>
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
            <details className="genetic-list">
              <summary>
                Accessible relationship list ({graph.nodes.length} visible
                cultures)
              </summary>
              <ul>
                {graph.nodes.map((n) => (
                  <li key={n.id}>
                    <button onClick={() => center(n.id)}>
                      {n.name} · {n.id} · {n.status}
                    </button>
                    {parents(n.id).map((e) => (
                      <p key={e.parent_id}>
                        {e.confidence} parent:{" "}
                        <button
                          onClick={() => {
                            const parent = data.nodes.find(
                              (n) => n.id === e.parent_id,
                            );
                            if (parent) focus(parent);
                          }}
                        >
                          {e.parent_id}
                        </button>
                      </p>
                    ))}
                    {!parents(n.id).length && <p>Unknown ancestry</p>}
                  </li>
                ))}
              </ul>
            </details>
          </section>
          <aside
            className="panel genetic-details"
            aria-label="Selected culture details"
          >
            {!selected ? (
              <>
                <Dna />
                <h2>Select a culture</h2>
                <p>
                  Explore a photograph to see its recorded origins and
                  descendants.
                </p>
              </>
            ) : (
              <>
                <Picture node={selected} />
                <h2>{selected.name}</h2>
                <p>
                  {selected.id} · {selected.status}
                </p>
                <p>
                  {data.strains.find((s) => s.id === selected.strain_id)
                    ?.name || "Unknown Strain"}{" "}
                  · {originNames[selected.origin_type]}
                </p>
                <p className="muted">
                  Photo: {selected.photo_source}
                  {selected.photo_source === "strain cover"
                    ? " (family fallback; not a culture photograph)"
                    : ""}
                </p>
                <h3>Recorded parents</h3>
                {parents(selected.id).map((e) => (
                  <p key={e.parent_id}>
                    <button
                      onClick={() => {
                        const n = data.nodes.find((n) => n.id === e.parent_id);
                        if (
                          n &&
                          !kingdom &&
                          (n.strain_id || "unknown") !== family
                        )
                          focus(n);
                        else center(e.parent_id);
                      }}
                    >
                      {e.parent_id}
                    </button>{" "}
                    · {e.confidence}
                    {data.nodes.find((n) => n.id === e.parent_id)?.strain_id !==
                    selected.strain_id
                      ? " · Different strain family"
                      : ""}
                  </p>
                ))}
                {!parents(selected.id).length && (
                  <p>Unknown ancestry. No parent inferred.</p>
                )}
                <h3>Recorded descendants</h3>
                {children(selected.id).map((e) => (
                  <p key={e.line_id}>
                    <button
                      onClick={() => {
                        const n = data.nodes.find((n) => n.id === e.line_id);
                        if (
                          n &&
                          !kingdom &&
                          (n.strain_id || "unknown") !== family
                        )
                          focus(n);
                        else center(e.line_id);
                      }}
                    >
                      {e.line_id}
                    </button>{" "}
                    · {e.confidence}
                  </p>
                ))}
                {selected.source && (
                  <p>
                    Original source:{" "}
                    <Link
                      to={`/culture-library/${selected.source.kind}/${selected.source.id}`}
                    >
                      {selected.source.id}
                    </Link>
                  </p>
                )}
                <div className="actions">
                  <Link to={`/culture-library/lines/${selected.id}`}>
                    Open Record
                  </Link>
                  <button onClick={() => focus(selected)}>
                    Focus on This Family
                  </button>
                  {selected.can_isolate && selected.status === "active" && (
                    <button onClick={() => launch("lines", selected.id)}>
                      Create Isolate
                    </button>
                  )}
                </div>
                {selected.fruiting_sources.length > 0 && (
                  <>
                    <label>
                      Recorded fruiting source
                      <select
                        value={source}
                        onChange={(e) => setSource(e.target.value)}
                      >
                        <option value="">Choose a source</option>
                        {selected.fruiting_sources.map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name} · {f.id}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      disabled={!source}
                      onClick={() => launch("fruiting", source)}
                    >
                      Establish Tissue Clone
                    </button>
                  </>
                )}
                {actionError && <p role="alert">{actionError}</p>}
                {workflow && (
                  <LineagePanel
                    record={workflow}
                    onChange={retry}
                    initialAction="establish"
                    onEstablished={(line) => {
                      setWorkflow(null);
                      setCollapsed(new Set());
                      setPendingFocus(line.id);
                      update({
                        node: line.id,
                        strain: line.strain_id || "unknown",
                      });
                      retry();
                    }}
                  />
                )}
                <h3>Associated photographs</h3>
                <p>
                  Line covers take priority. Representative choices keep their
                  original ownership.
                </p>
                <div className="genetic-photos">
                  {selected.photos.map((p) => (
                    <div key={p.id}>
                      <img
                        src={p.thumbnail_url}
                        alt={`Associated photograph from ${p.owner_id}`}
                      />
                      <small>
                        {p.owner_id}
                        {p.line_cover ? " · Line cover" : ""}
                      </small>
                      <button onClick={() => choose(p.id)}>
                        Use as Genetic Tree Photo
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={() => choose(null)}>
                  Clear representative photo
                </button>
              </>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
