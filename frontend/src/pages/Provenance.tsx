import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "../components/UI";
import { Field } from "./LibraryForms";
import { LabelChoices } from "../components/ContainerTracking";
import type { LabelChoice } from "../containerApi";
import {
  allLibraryRecords,
  libraryApi,
  provenanceApi,
  localToday,
  title,
  cultureTypes,
  sporeTypes,
  units,
  growTypes,
  origins,
} from "../libraryApi";
import type { LibraryRecord, Provenance } from "../libraryApi";

type Values = Record<string, string>;
const failure = (e: unknown) =>
  e instanceof Error ? e.message : "Unable to save. Please retry.";
const optional = (value: string) => value.trim() || null;
const quantityFields = (
  v: Values | { quantity: string; unit: string; storage_location: string },
) => ({
  quantity: optional(v.quantity),
  unit: optional(v.unit),
  storage_location: optional(v.storage_location),
});
function useChoices() {
  const [choices, setChoices] = useState<Record<
    string,
    LibraryRecord[]
  > | null>(null);
  const [error, setError] = useState("");
  const [revision, retry] = useState(0);
  useEffect(() => {
    let live = true;
    Promise.all(
      ["strains", "lines", "spawn"].map(
        async (k) => [k, await allLibraryRecords(k)] as const,
      ),
    )
      .then((entries) => {
        if (live) {
          setChoices(Object.fromEntries(entries));
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(failure(e));
      });
    return () => {
      live = false;
    };
  }, [revision]);
  return { choices, error, retry: () => retry(revision + 1) };
}
function QuantityFields({
  values,
  set,
}: {
  values: Values;
  set: (n: string, v: string) => void;
}) {
  return (
    <>
      <Field
        name="quantity"
        label="Starting quantity (optional)"
        type="number"
        values={values}
        set={set}
      />
      <Field
        name="unit"
        label="Quantity unit"
        values={values}
        set={set}
        options={{ "": "Unknown", ...units }}
      />
      <Field
        name="storage_location"
        label="Storage location"
        values={values}
        set={set}
      />
    </>
  );
}
export function AcquisitionForm() {
  const { choices, error: loadError, retry } = useChoices();
  const navigate = useNavigate();
  const [v, setV] = useState<Values>({
    entry_type: "spawn_jar",
    origin: "purchased",
    strain_mode: "unknown",
    strain_id: "",
    strain_name: "",
    existing_line_id: "",
    name: "",
    notes: "",
    supplier: "",
    supplier_reference: "",
    supplier_batch: "",
    acquisition_date: localToday(),
    count: "1",
    quantity: "",
    unit: "",
    storage_location: "",
    stage: "ready",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState(false);
  const set = (n: string, value: string) => {
    setV({
      ...v,
      [n]: value,
      ...(["strain_mode", "strain_id"].includes(n)
        ? { existing_line_id: "" }
        : {}),
    });
    setReview(false);
  };
  const spores = v.entry_type in sporeTypes;
  const culture = v.entry_type in cultureTypes;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!review) {
      setReview(true);
      return;
    }
    setBusy(true);
    try {
      const strain =
        v.strain_mode === "new"
          ? { inline_strain: { name: v.strain_name } }
          : { strain_id: v.strain_mode === "existing" ? v.strain_id : null };
      const acquisition = {
        supplier: optional(v.supplier),
        supplier_reference: optional(v.supplier_reference),
        acquisition_date: optional(v.acquisition_date),
      };
      const descriptive = { name: optional(v.name), notes: optional(v.notes) };
      let saved: LibraryRecord;
      if (spores) {
        saved = await libraryApi<LibraryRecord>("spores", "POST", {
          ...strain,
          ...acquisition,
          ...descriptive,
          ...quantityFields(v),
          material_type: v.entry_type,
        });
      } else {
        const lineage = v.existing_line_id
          ? { existing_line_id: v.existing_line_id }
          : {
              line: {
                ...acquisition,
                ...descriptive,
                supplier_batch: optional(v.supplier_batch),
                origin: v.origin,
              },
            };
        const result = await provenanceApi<{
          line: LibraryRecord;
          records: LibraryRecord[];
        }>("acquisitions", "POST", {
          ...strain,
          ...lineage,
          entry_type: culture ? "culture" : v.entry_type,
          ...(culture
            ? {
                material: {
                  ...descriptive,
                  ...quantityFields(v),
                  material_type: v.entry_type,
                  count: Number(v.count),
                },
              }
            : {
                ...descriptive,
                ...quantityFields(v),
                ...acquisition,
                supplier_batch: optional(v.supplier_batch),
                count: Number(v.count),
                stage: v.stage,
              }),
        });
        saved = result.records[0] ?? result.line;
      }
      navigate(`/culture-library/${saved.kind}/${saved.id}`, {
        state: {
          message:
            "Acquisition registered. Attach photographs to individual records below.",
        },
      });
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  if (!choices)
    return (
      <div className="feedback">
        {loadError ? (
          <>
            <p role="alert">{loadError}</p>
            <button onClick={retry}>Retry</button>
          </>
        ) : (
          "Loading acquisition choices…"
        )}
      </div>
    );
  const compatible = choices.lines.filter(
    (l) =>
      l.strain_id === (v.strain_mode === "existing" ? v.strain_id : null) &&
      v.strain_mode !== "new",
  );
  return (
    <>
      <Link to="/acquisitions">← Acquisitions</Link>
      <PageHeader
        title="Receive Acquisition"
        description="Start tracking at the stage you acquired. Earlier cultivation history stays unknown."
      />
      <form className="library-form panel" onSubmit={submit}>
        {!review ? (
          <>
            <Field
              name="entry_type"
              label="Acquired material"
              values={v}
              set={set}
              options={{
                ...cultureTypes,
                ...sporeTypes,
                spawn_jar: growTypes.spawn_jar,
                spawn_bag: growTypes.spawn_bag,
                fruiting_bag: "Ready-to-fruit bag",
                fruiting_block: "Ready-to-fruit block",
              }}
            />
            <Field
              name="strain_mode"
              label="Strain selection"
              values={v}
              set={set}
              options={{
                unknown: "Strain currently unknown",
                existing: "Select existing strain",
                new: "Create strain inline",
              }}
            />
            {v.strain_mode === "new" && (
              <Field
                name="strain_name"
                label="Strain name"
                required
                values={v}
                set={set}
              />
            )}
            {v.strain_mode === "existing" && (
              <Field
                name="strain_id"
                label="Strain"
                required
                values={v}
                set={set}
                options={{
                  "": "Choose a strain",
                  ...Object.fromEntries(
                    choices.strains.map((s) => [s.id, `${title(s)} · ${s.id}`]),
                  ),
                }}
              />
            )}
            {!spores && (
              <Field
                name="existing_line_id"
                label="Culture line"
                values={v}
                set={set}
                options={{
                  "": "Create independent acquired line",
                  ...Object.fromEntries(
                    compatible.map((l) => [l.id, `${title(l)} · ${l.id}`]),
                  ),
                }}
              />
            )}
            {!spores && !v.existing_line_id && (
              <Field
                name="origin"
                label="Acquisition origin"
                values={v}
                set={set}
                options={origins}
              />
            )}
            <Field
              name="supplier"
              label="Supplier / source"
              values={v}
              set={set}
            />
            <Field
              name="supplier_reference"
              label="Supplier reference"
              values={v}
              set={set}
            />
            {!spores && (
              <Field
                name="supplier_batch"
                label="Supplier batch identifier"
                values={v}
                set={set}
              />
            )}
            <Field
              name="acquisition_date"
              label="Acquisition date (optional)"
              type="date"
              values={v}
              set={set}
            />
            {!spores && (
              <Field
                name="count"
                label="Number of containers (1–100)"
                type="number"
                required
                values={v}
                set={set}
              />
            )}
            {!spores && !culture && (
              <Field
                name="stage"
                label="Material stage"
                values={v}
                set={set}
                options={{ ready: "Ready", colonizing: "Colonizing" }}
              />
            )}
            <Field name="name" label="Optional name" values={v} set={set} />
            <QuantityFields values={v} set={set} />
            <Field
              name="notes"
              label="Notes"
              type="textarea"
              values={v}
              set={set}
            />
          </>
        ) : (
          <>
            <h2>Review acquisition</h2>
            <p>
              {v.count} ×{" "}
              {
                (
                  {
                    ...cultureTypes,
                    ...sporeTypes,
                    ...growTypes,
                    fruiting_bag: "Ready-to-fruit bag",
                    fruiting_block: "Ready-to-fruit block",
                  } as Values
                )[v.entry_type]
              }
            </p>
            <p>
              Strain:{" "}
              {v.strain_mode === "new"
                ? v.strain_name
                : choices.strains.find((s) => s.id === v.strain_id)?.name ||
                  "Unknown"}
            </p>
            <p>
              {spores
                ? "A spore source only; no culture line."
                : v.existing_line_id
                  ? `Existing culture line ${v.existing_line_id}`
                  : "A new independent acquired line; genetic ancestry unknown."}
            </p>
            {v.entry_type.startsWith("fruiting_") && (
              <p>
                An acquired Grow Batch and permanent FR identifiers will be
                created. No substrate recipe or external spawn history is
                asserted.
              </p>
            )}
            <p>
              Quantity: {v.quantity || "Unknown"} {v.unit} · {v.stage}
            </p>
            <p>
              Supplier: {v.supplier || "Unknown"} · Date:{" "}
              {v.acquisition_date || "Unknown"}
            </p>
            <button type="button" onClick={() => setReview(false)}>
              Back
            </button>
          </>
        )}
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button className="primary" disabled={busy}>
            {busy
              ? "Saving…"
              : review
                ? "Confirm acquisition"
                : "Review acquisition"}
          </button>
          <Link to="/acquisitions">Cancel</Link>
        </div>
      </form>
    </>
  );
}

export function GrowForm() {
  const { choices, error: loadError, retry } = useChoices();
  const navigate = useNavigate();
  const [v, setV] = useState<Values>({
    name: "",
    notes: "",
    allocation_mode: "shared",
    acquisition_date: localToday(),
  });
  const [sources, setSources] = useState<string[]>([]);
  const empty = () => ({
    name: "",
    material_type: "tray",
    stage: "ready",
    notes: "",
    quantity: "",
    unit: "",
    storage_location: "",
    acquisition_date: "",
    source_ids: [] as string[],
    reusable: false,
    label_choice: {} as LabelChoice,
  });
  const [containers, setContainers] = useState([empty()]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const selected = choices?.spawn.filter((s) => sources.includes(s.id)) ?? [];
  const mixedLines = new Set(selected.map((s) => s.line_id)).size > 1;
  const mixedStrains =
    new Set(selected.map((s) => s.strain_id).filter(Boolean)).size > 1;
  const toggle = (ids: string[], id: string) =>
    ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id];
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await provenanceApi<{ batch: LibraryRecord }>(
        "grows",
        "POST",
        {
          ...v,
          name: optional(v.name),
          notes: optional(v.notes),
          acquisition_date: optional(v.acquisition_date),
          source_ids: sources,
          containers: containers.map((c) => ({
            ...c,
            reusable: undefined,
            label_choice: {
              ...c.label_choice,
              ...(c.material_type === "other" ? { reusable: c.reusable } : {}),
            },
            ...quantityFields(c),
            name: optional(c.name),
            notes: optional(c.notes),
            acquisition_date: optional(c.acquisition_date),
            source_ids: v.allocation_mode === "shared" ? [] : c.source_ids,
          })),
        },
      );
      navigate(`/culture-library/batches/${result.batch.id}`);
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  if (!choices)
    return (
      <div className="feedback">
        {loadError ? (
          <>
            <p role="alert">{loadError}</p>
            <button onClick={retry}>Retry</button>
          </>
        ) : (
          "Loading spawn choices…"
        )}
      </div>
    );
  return (
    <>
      <Link to="/culture-library">← Culture Library</Link>
      <PageHeader
        title="Register Grow Provenance"
        description="Document a user-prepared grow and known sources. This does not execute spawning or consume material."
      />
      <form className="library-form panel" onSubmit={submit}>
        <Field
          name="name"
          label="Grow batch name (optional)"
          values={v}
          set={(n, value) => setV({ ...v, [n]: value })}
        />
        <Field
          name="acquisition_date"
          label="Registration date (optional)"
          type="date"
          values={v}
          set={(n, value) => setV({ ...v, [n]: value })}
        />
        <fieldset>
          <legend>Known source spawn jars / bags</legend>
          {!choices.spawn.length && (
            <p>
              No spawn registered. You may leave sources unknown or receive an
              acquisition first.
            </p>
          )}
          {choices.spawn.map((s) => (
            <label className="checkbox" key={s.id}>
              <input
                type="checkbox"
                checked={sources.includes(s.id)}
                onChange={() => {
                  setSources(toggle(sources, s.id));
                  setContainers(
                    containers.map((c) => ({
                      ...c,
                      source_ids: c.source_ids.filter((id) => id !== s.id),
                    })),
                  );
                }}
              />
              {s.physical_label || s.id}
              {s.physical_label ? ` (record ${s.id})` : ""} ·{" "}
              {s.strain_name || "Unknown strain"} · {s.line_id} · {s.stage}
            </label>
          ))}
        </fieldset>
        {mixedLines && (
          <p role="status" className="provenance-warning">
            Mixed culture lines: this does not imply hybridization.
          </p>
        )}
        {mixedStrains && (
          <p role="status" className="provenance-warning">
            Mixed named strains: no synthetic strain will be created.
          </p>
        )}
        <Field
          name="allocation_mode"
          label="Source allocation"
          values={v}
          set={(n, value) => setV({ ...v, [n]: value })}
          options={{
            shared:
              "Shared mixture — each container inherits all known sources",
            specific: "Specific allocation — record sources per container",
          }}
        />
        <p>
          Leave unknown sources unselected. One jar may contribute to several
          containers. These links are manual provenance and do not mark jars
          Used.
        </p>
        {containers.map((c, i) => (
          <fieldset key={i}>
            <legend>Fruiting container {i + 1}</legend>
            {(
              [
                "name",
                "material_type",
                "stage",
                "acquisition_date",
                "quantity",
                "unit",
                "storage_location",
                "notes",
              ] as const
            ).map((n) => (
              <Field
                key={n}
                name={`container_${i}_${n}`}
                label={
                  {
                    name: "Container name (optional)",
                    material_type: "Container type",
                    stage: "Stage",
                    acquisition_date: "Registration date (optional)",
                    quantity: "Starting quantity (optional)",
                    unit: "Quantity unit",
                    storage_location: "Location",
                    notes: "Container notes",
                  }[n]
                }
                values={{ [`container_${i}_${n}`]: c[n] }}
                set={(_, value) =>
                  setContainers(
                    containers.map((item, j) =>
                      j === i
                        ? {
                            ...item,
                            [n]: value,
                            ...(n === "material_type"
                              ? { label_choice: {} }
                              : {}),
                          }
                        : item,
                    ),
                  )
                }
                type={
                  n === "quantity"
                    ? "number"
                    : n === "notes"
                      ? "textarea"
                      : n === "acquisition_date"
                        ? "date"
                        : "text"
                }
                options={
                  n === "material_type"
                    ? {
                        tray: "Tray",
                        bag: "Bag",
                        block: "Block",
                        other: "Other",
                      }
                    : n === "stage"
                      ? {
                          ready: "Ready",
                          colonizing: "Colonizing",
                          fruiting: "Fruiting",
                          finished: "Finished",
                        }
                      : n === "unit"
                        ? { "": "Unknown", ...units }
                        : undefined
                }
              />
            ))}
            {c.material_type === "other" && (
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={c.reusable}
                  onChange={(e) =>
                    setContainers(
                      containers.map((row, j) =>
                        j === i
                          ? {
                              ...row,
                              reusable: e.target.checked,
                              label_choice: {},
                            }
                          : row,
                      ),
                    )
                  }
                />
                Physically reusable fruiting container
              </label>
            )}
            <LabelChoices
              key={`${c.material_type}-${c.reusable}`}
              material={c.material_type}
              reusable={c.material_type === "other" ? c.reusable : undefined}
              count={1}
              choices={[c.label_choice]}
              onChange={(choice) =>
                setContainers(
                  containers.map((row, j) =>
                    j === i ? { ...row, label_choice: choice[0] || {} } : row,
                  ),
                )
              }
            />
            {v.allocation_mode === "specific" && (
              <fieldset>
                <legend>
                  Sources for container {i + 1} (leave empty if unknown)
                </legend>
                {selected.map((s) => (
                  <label className="checkbox" key={s.id}>
                    <input
                      type="checkbox"
                      checked={c.source_ids.includes(s.id)}
                      onChange={() =>
                        setContainers(
                          containers.map((item, j) =>
                            j === i
                              ? {
                                  ...item,
                                  source_ids: toggle(item.source_ids, s.id),
                                }
                              : item,
                          ),
                        )
                      }
                    />
                    {s.physical_label || s.id}
                    {s.physical_label ? ` (record ${s.id})` : ""} · {s.line_id}
                  </label>
                ))}
              </fieldset>
            )}
            {containers.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setContainers(containers.filter((_, j) => j !== i))
                }
              >
                Remove container {i + 1}
              </button>
            )}
          </fieldset>
        ))}
        <button
          type="button"
          disabled={containers.length >= 100}
          onClick={() => setContainers([...containers, empty()])}
        >
          Add fruiting container
        </button>
        <Field
          name="notes"
          label="Batch notes"
          type="textarea"
          values={v}
          set={(n, value) => setV({ ...v, [n]: value })}
        />
        {error && <p role="alert">{error}</p>}
        <div className="actions">
          <button className="primary" disabled={busy}>
            {busy ? "Saving…" : "Register manual provenance"}
          </button>
          <Link to="/culture-library">Cancel</Link>
        </div>
      </form>
    </>
  );
}

export function LineagePanel({
  record,
  onChange,
}: {
  record: LibraryRecord;
  onChange: () => void;
}) {
  const [data, setData] = useState<Provenance | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [action, setAction] = useState("");
  const [busy, setBusy] = useState(false);
  const [v, setV] = useState<Values>({
    name: "",
    notes: "",
    origin_date: "",
    material_type: "none",
    count: "1",
    quantity: "",
    unit: "",
    storage_location: "",
    collection_date: "",
    spore_type: "spore_print",
    reason: "",
    parent_id: "",
    confidence: "confirmed",
    unknown_strain: "false",
  });
  const [lines, setLines] = useState<LibraryRecord[]>([]);
  useEffect(() => {
    let live = true;
    setData(null);
    setAction("");
    setError("");
    provenanceApi<Provenance>(`${record.kind}/${record.id}`)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => {
        if (live) setError(failure(e));
      });
    return () => {
      live = false;
    };
  }, [record, revision]);
  useEffect(() => {
    if (action !== "correct") return;
    let live = true;
    allLibraryRecords("lines?status=all")
      .then((l) => {
        if (live) setLines(l);
      })
      .catch((e) => {
        if (live) setError(failure(e));
      });
    return () => {
      live = false;
    };
  }, [action]);
  const navigate = useNavigate();
  const set = (n: string, value: string) => setV({ ...v, [n]: value });
  const labels: Values = {
    lines: "Create Isolate",
    spores: "Establish Culture",
    fruiting: "Establish Tissue Clone",
  };
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (action === "correct") {
        await provenanceApi(`lines/${record.id}/ancestry`, "PUT", {
          expected_revision: data?.revision,
          reason: v.reason,
          parents: v.parent_id
            ? [{ parent_id: v.parent_id, confidence: v.confidence }]
            : [],
        });
        setAction("");
        setRevision(revision + 1);
        onChange();
      } else if (action === "collect") {
        const saved = await provenanceApi<LibraryRecord>(
          `fruiting/${record.id}/collect`,
          "POST",
          {
            name: optional(v.name),
            notes: optional(v.notes),
            collection_date: optional(v.collection_date),
            material_type: v.spore_type,
            ...quantityFields(v),
          },
        );
        navigate(`/culture-library/spores/${saved.id}`);
      } else {
        const result = await provenanceApi<{ line: LibraryRecord }>(
          `${record.kind}/${record.id}/establish`,
          "POST",
          {
            name: optional(v.name),
            notes: optional(v.notes),
            origin_date: optional(v.origin_date),
            unknown_strain: v.unknown_strain === "true",
            material:
              v.material_type === "none"
                ? null
                : {
                    material_type: v.material_type,
                    count: Number(v.count),
                    ...quantityFields(v),
                  },
          },
        );
        navigate(`/culture-library/lines/${result.line.id}`);
      }
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel lineage-panel">
      <h2>Ancestry &amp; provenance</h2>
      {error && (
        <div role="alert">
          {error}
          <button type="button" onClick={() => setRevision(revision + 1)}>
            Reload relationships
          </button>
        </div>
      )}
      {!data ? (
        <p role="status">Loading relationships…</p>
      ) : (
        <>
          <dl className="info-list">
            <div>
              <dt>Biological / batch origin</dt>
              <dd>{data.origin_type || "Unknown"}</dd>
            </div>
            {record.kind === "lines" && (
              <div>
                <dt>Genetic ancestry</dt>
                <dd>
                  <span className="badge">{data.ancestry_status}</span>
                </dd>
              </div>
            )}
            {data.origin_date && (
              <div>
                <dt>Origin / collection date</dt>
                <dd>{data.origin_date}</dd>
              </div>
            )}
            {data.allocation_mode && (
              <div>
                <dt>Allocation</dt>
                <dd>
                  {data.allocation_mode === "shared"
                    ? "Shared mixture"
                    : "Specific allocation"}
                </dd>
              </div>
            )}
          </dl>
          {data.notes && <p>{data.notes}</p>}
          {data.warnings.map((w) => (
            <p className="provenance-warning" key={w}>
              {w}
            </p>
          ))}
          {["spawn", "batches", "fruiting"].includes(record.kind) && (
            <p className="muted">{data.provenance_mode}</p>
          )}
          <ul className="record-list">
            {data.relationships.map(({ label, record: r }) => (
              <li key={`${label}/${r.id}`}>
                <span className="relationship-label">{label}</span>
                <Link to={`/culture-library/${r.kind}/${r.id}`}>
                  {title(r)} · {r.id} · {r.status}
                </Link>
              </li>
            ))}
          </ul>
          {!data.relationships.length && (
            <p>No documented relationships. Unknown ancestry is preserved.</p>
          )}
          {record.status === "active" && (
            <div className="actions">
              {labels[record.kind] && (
                <button onClick={() => setAction("establish")}>
                  {labels[record.kind]}
                </button>
              )}
              {record.kind === "fruiting" && (
                <button onClick={() => setAction("collect")}>
                  Collect Spores
                </button>
              )}
              {record.kind === "lines" && data.origin_type !== "isolate" && (
                <button onClick={() => setAction("correct")}>
                  Correct ancestry
                </button>
              )}
            </div>
          )}
          {action && (
            <form className="library-form" onSubmit={submit}>
              <h3>
                {action === "correct"
                  ? "Correct genetic ancestry"
                  : action === "collect"
                    ? "Collect Spores"
                    : labels[record.kind]}
              </h3>
              {action === "correct" ? (
                <>
                  <p>
                    This replaces the genetic parent selection. Physical sources
                    stay linked. Previous ancestry and your reason are retained
                    in activity history.
                  </p>
                  {data.parents.length > 0 && (
                    <p>
                      Current:{" "}
                      {data.parents
                        .map((p) => `${p.parent_id} (${p.confidence})`)
                        .join(", ")}
                    </p>
                  )}
                  <Field
                    name="parent_id"
                    label="Confirmed parent (or restore unknown ancestry)"
                    values={v}
                    set={set}
                    options={{
                      "": "Unknown — no genetic parent asserted",
                      ...Object.fromEntries(
                        lines
                          .filter(
                            (l) =>
                              l.id !== record.id &&
                              (data.origin_type !== "clone" ||
                                data.relationships.some(
                                  (r) =>
                                    r.label ===
                                      "Documented fruiting source line · not a parent assertion" &&
                                    r.record.id === l.id,
                                )),
                          )
                          .map((l) => [l.id, `${title(l)} · ${l.id}`]),
                      ),
                    }}
                  />
                  <Field
                    name="reason"
                    label="Correction reason"
                    required
                    type="textarea"
                    values={v}
                    set={set}
                  />
                </>
              ) : (
                <>
                  <p>
                    {action === "collect"
                      ? "Register physical collection provenance. Mixed source strains remain unassigned."
                      : "Register a successfully established culture only. Failed attempts and routine transfers are not recorded here."}
                  </p>
                  <Field
                    name="name"
                    label="Optional name"
                    values={v}
                    set={set}
                  />
                  <Field
                    name={
                      action === "collect" ? "collection_date" : "origin_date"
                    }
                    label={
                      action === "collect"
                        ? "Collection date (optional)"
                        : "Establishment date (optional)"
                    }
                    type="date"
                    values={v}
                    set={set}
                  />
                  <Field
                    name="notes"
                    label="Notes"
                    type="textarea"
                    values={v}
                    set={set}
                  />
                  {action !== "collect" && record.kind !== "lines" && (
                    <Field
                      name="unknown_strain"
                      label="Strain identity"
                      values={v}
                      set={set}
                      options={{
                        false: "Carry reported source strain when unambiguous",
                        true: "Keep new line strain unknown",
                      }}
                    />
                  )}
                  {action === "collect" ? (
                    <Field
                      name="spore_type"
                      label="Spore material type"
                      values={v}
                      set={set}
                      options={sporeTypes}
                    />
                  ) : (
                    <Field
                      name="material_type"
                      label="Initial physical material (optional)"
                      values={v}
                      set={set}
                      options={{
                        none: "No initial container",
                        ...cultureTypes,
                      }}
                    />
                  )}
                  {action !== "collect" && v.material_type !== "none" && (
                    <Field
                      name="count"
                      label="Number of containers (1–100)"
                      required
                      type="number"
                      values={v}
                      set={set}
                    />
                  )}
                  {(action === "collect" || v.material_type !== "none") && (
                    <QuantityFields values={v} set={set} />
                  )}
                </>
              )}
              <div className="actions">
                <button className="primary" disabled={busy}>
                  {busy ? "Saving…" : "Save"}
                </button>
                <button type="button" onClick={() => setAction("")}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
