import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  Link,
  useParams,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import { PageHeader } from "../components/UI";
import { Field } from "./LibraryForms";
import { allLibraryRecords, localToday, provenanceApi } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import {
  preparationApi,
  useInventoryCommand,
  useInventoryList,
  materialNames,
  stockUnits,
  stageName,
  compatibleUnits,
} from "../preparationApi";
import type {
  Stock,
  Prepared,
  Ledger,
  Ingredient,
  Pool,
} from "../preparationApi";

type Values = Record<string, string>;
export function InventoryNav() {
  return (
    <nav className="actions inventory-nav" aria-label="Inventory sections">
      <Link to="/inventory">Inventory</Link>
      <Link to="/inventory/stock">Ingredients & Supplies</Link>
      <details>
        <summary>Previous preparation & accounting</summary>
        <div className="actions">
          <Link to="/inventory/prepared">Previous prepared materials</Link>
          <Link to="/inventory/transactions">Accounting history</Link>
        </div>
      </details>
    </nav>
  );
}
function Feedback({ error, retry }: { error: string; retry: () => void }) {
  return error ? (
    <div role="alert">
      {error}
      <button onClick={retry}>Retry</button>
    </div>
  ) : (
    <p role="status">Loading inventory…</p>
  );
}
export function StockForm({
  initial = {},
  onSaved,
}: {
  initial?: Values;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    name: "",
    category: "ingredient",
    unit: "g",
    available: "",
    reason: "",
    notes: "",
    storage_location: "",
    container_type: "",
    source_kind: "physical",
    source_id: "",
    ...initial,
  });
  const [sources, setSources] = useState<LibraryRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const command = useInventoryCommand();
  useEffect(() => {
    if (v.category !== "source") return;
    let live = true;
    Promise.all([
      allLibraryRecords("physical?status=all"),
      allLibraryRecords("spores?status=all"),
    ])
      .then((groups) => {
        if (live) {
          setSources(groups.flat());
          setLoadError("");
        }
      })
      .catch((e) => {
        if (live) setLoadError(e.message);
      });
    return () => {
      live = false;
    };
  }, [v.category, attempt]);
  const set = (n: string, value: string) =>
    setV({
      ...v,
      [n]: value,
      ...(n === "category"
        ? {
            unit: ["reusable", "consumable", "equipment", "other"].includes(
              value,
            )
              ? "count"
              : value === "source"
                ? "mL"
                : "g",
            container_type: "",
            source_id: "",
          }
        : {}),
    });
  async function submit(e: FormEvent) {
    e.preventDefault();
    const source = sources.find(
      (s) => `${s.kind}:${s.id}` === `${v.source_kind}:${v.source_id}`,
    );
    if (v.category === "source" && !source) return;
    const result = await command.send<Stock>("stock", {
      name: v.name,
      category: v.category,
      unit: v.unit,
      available: v.available || null,
      reason: v.reason,
      notes: v.notes || null,
      storage_location: v.storage_location || null,
      container_type: ["reusable", "consumable"].includes(v.category)
        ? v.container_type || null
        : null,
      ...(v.category === "source"
        ? { source_kind: v.source_kind, source_id: v.source_id }
        : {}),
    });
    if (result) onSaved();
  }
  return (
    <form className="library-form panel workflow-form" onSubmit={submit}>
      <h2>Add Inventory</h2>
      <p>
        Enter a confirmed available quantity, or leave unknown where permitted.
        Opening quantities are never seeded or copied from acquisition
        measurements.
      </p>
      <Field name="name" label="Inventory name" required values={v} set={set} />
      <Field
        name="category"
        label="Inventory category"
        values={v}
        set={set}
        options={{
          reusable: "Reusable Containers",
          ingredient: "Raw Ingredients",
          consumable: "Disposable Supplies",
          equipment: "Equipment",
          other: "Other Supplies",
          ...(initial.category === "source"
            ? { source: "Remaining Culture Material" }
            : {}),
        }}
      />
      {v.category === "source" && (
        <>
          <p>
            LC volumes use mL. An unknown balance records usage without guessing
            what remains.
          </p>
          {loadError && (
            <p role="alert">
              {loadError}
              <button type="button" onClick={() => setAttempt(attempt + 1)}>
                Retry source records
              </button>
            </p>
          )}
          <label className="field">
            <span id="stock-source-label">Biological source record</span>
            <select
              aria-labelledby="stock-source-label"
              required
              value={`${v.source_kind}:${v.source_id}`}
              onChange={(e) => {
                const s = sources.find(
                  (s) => `${s.kind}:${s.id}` === e.target.value,
                );
                if (s)
                  setV({
                    ...v,
                    source_kind: s.kind,
                    source_id: s.id,
                    unit: s.material_type?.startsWith("lc_")
                      ? "mL"
                      : s.unit || "count",
                  });
              }}
            >
              <option value="physical:">Choose source</option>
              {sources.map((s) => (
                <option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>
                  {s.id} · {s.strain_name || "Unknown strain"} · {s.status}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {["reusable", "consumable"].includes(v.category) && (
        <Field
          name="container_type"
          label="Container supply type"
          values={v}
          set={set}
          required={v.category === "reusable"}
          options={{
            "": "Other consumable",
            ...Object.fromEntries(
              Object.entries(materialNames).filter(([type]) =>
                v.category === "reusable"
                  ? [
                      "agar_plate",
                      "lc_jar",
                      "spawn_jar",
                      "fruiting_tray",
                    ].includes(type)
                  : ["lc_syringe", "spawn_bag"].includes(type),
              ),
            ),
          }}
        />
      )}
      <Field
        name="unit"
        label="Inventory unit"
        values={v}
        set={set}
        options={v.category === "reusable" ? { count: "Count" } : stockUnits}
      />
      <Field
        name="available"
        label={
          v.category === "reusable"
            ? "Confirmed free container count"
            : "Confirmed available quantity (blank = unknown)"
        }
        type="number"
        required={v.category === "reusable"}
        values={v}
        set={set}
      />
      <Field
        name="reason"
        label="Opening balance reason"
        type="textarea"
        required
        values={v}
        set={set}
      />
      <Field
        name="storage_location"
        label="Storage location (optional)"
        values={v}
        set={set}
      />
      <Field
        name="notes"
        label="Inventory notes"
        type="textarea"
        values={v}
        set={set}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <button
        className="primary"
        disabled={
          command.busy ||
          (v.category === "source" &&
            !sources.some(
              (s) => s.kind === v.source_kind && s.id === v.source_id,
            ))
        }
      >
        {command.busy ? "Saving…" : "Add Inventory"}
      </button>
    </form>
  );
}
function AdjustmentForm({
  item,
  onSaved,
}: {
  item: Stock;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    mode: "add",
    quantity: "",
    unit: item.unit,
    reason: "",
  });
  const command = useInventoryCommand();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await command.send<Stock>(`stock/${item.id}/adjust`, {
      mode: v.mode,
      quantity: v.quantity || null,
      expected_revision: item.revision,
      unit: v.unit,
      reason: v.reason,
    });
    if (r) onSaved();
  }
  return (
    <form className="library-form panel workflow-form" onSubmit={submit}>
      <h2>
        Adjust {item.name} · {item.id}
      </h2>
      <p>
        Current free/available balance: {item.available ?? "Unknown"}{" "}
        {item.unit}. Additions to an unknown balance keep it unknown; a measured
        correction explicitly establishes a known balance. Pool adjustments
        refer to free, unreserved containers.
      </p>
      <Field
        name="mode"
        label="Adjustment type"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
        options={{
          add: "Stock addition",
          correct: "Correct measured available balance",
        }}
      />
      <Field
        name="quantity"
        label="Adjustment quantity (blank correction = unknown)"
        type="number"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
        required={v.mode === "add" || item.category === "reusable"}
      />
      <Field
        name="unit"
        label="Adjustment unit"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
        options={compatibleUnits(item.unit)}
      />
      <Field
        name="reason"
        label="Adjustment reason"
        required
        type="textarea"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <button disabled={command.busy}>Record Adjustment</button>
    </form>
  );
}
function StockMetadataForm({
  item,
  onSaved,
}: {
  item: Stock;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    name: item.name,
    storage_location: item.storage_location || "",
    notes: item.notes || "",
    reason: "",
  });
  const command = useInventoryCommand();
  return (
    <form
      className="library-form panel workflow-form"
      onSubmit={async (e) => {
        e.preventDefault();
        if (
          await command.send(
            `stock/${item.id}`,
            {
              ...v,
              storage_location: v.storage_location || null,
              notes: v.notes || null,
              expected_revision: item.revision,
            },
            "PUT",
          )
        )
          onSaved();
      }}
    >
      <h2>Edit {item.name}</h2>
      <Field
        name="edit_name"
        label="Item name"
        required
        values={{ edit_name: v.name }}
        set={(_, x) => setV({ ...v, name: x })}
      />
      <Field
        name="edit_location"
        label="Storage location"
        values={{ edit_location: v.storage_location }}
        set={(_, x) => setV({ ...v, storage_location: x })}
      />
      <Field
        name="edit_notes"
        label="Item notes"
        type="textarea"
        values={{ edit_notes: v.notes }}
        set={(_, x) => setV({ ...v, notes: x })}
      />
      <Field
        name="edit_reason"
        label="Edit reason"
        required
        values={{ edit_reason: v.reason }}
        set={(_, x) => setV({ ...v, reason: x })}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <div className="actions">
        <button className="primary" disabled={command.busy}>
          Save Item
        </button>
      </div>
    </form>
  );
}
export function StockPage({
  title = "Ingredients & Supplies",
}: {
  title?: string;
}) {
  const { data, error, reload } = useInventoryList<Stock>("stock");
  const [params] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [initial, setInitial] = useState<Values>({});
  const [adjust, setAdjust] = useState<Stock | null>(null);
  const [editing, setEditing] = useState<Stock | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (params.get("add") === "1") setOpen(true);
    if (params.get("source_id")) {
      setInitial({
        category: "source",
        unit: "mL",
        source_kind: params.get("source_kind") || "physical",
        source_id: params.get("source_id")!,
        name: `Source ${params.get("source_id")}`,
      });
      setOpen(true);
    }
  }, [params]);
  useEffect(() => {
    const code = params.get("item");
    if (code && data) {
      const item = data.find((row) => row.id === code);
      if (item) {
        setAdjust(item);
        setOpen(false);
      }
    }
  }, [params, data]);
  return (
    <>
      <InventoryNav />
      <PageHeader
        title={title}
        description="Optional stock records. Cultures can be created without registering ingredients or containers."
      />
      {!data ? (
        <Feedback error={error} retry={reload} />
      ) : (
        <>
          {error && (
            <p role="alert">
              {error}
              <button onClick={reload}>Reload stock</button>
            </p>
          )}
          {notice && <p role="status">{notice}</p>}
          <div className="actions">
            <button
              className="primary"
              onClick={() => {
                setInitial({});
                setOpen(true);
                setAdjust(null);
              }}
            >
              + Add Inventory
            </button>
          </div>
          <details>
            <summary>Previous reusable container pools</summary>
            <PoolOverview
              key={data.map((s) => `${s.id}:${s.revision}`).join(",")}
            />
          </details>
          {open && (
            <StockForm
              key={JSON.stringify(initial)}
              initial={initial}
              onSaved={() => {
                setOpen(false);
                setNotice("Opening inventory recorded.");
                reload();
              }}
            />
          )}
          {editing && (
            <StockMetadataForm
              key={editing.id + editing.revision}
              item={editing}
              onSaved={() => {
                setEditing(null);
                setNotice("Item updated.");
                reload();
              }}
            />
          )}
          {adjust && (
            <AdjustmentForm
              key={adjust.id + adjust.revision}
              item={adjust}
              onSaved={() => {
                setAdjust(null);
                setNotice("Adjustment recorded.");
                reload();
              }}
            />
          )}
          {!data.length && (
            <p className="feedback">
              No stock configured. Open your actual ingredients, supplies and
              reusable pools to begin.
            </p>
          )}
          <ul className="record-list panel">
            {data
              .filter((item) => item.category !== "source")
              .map((item) => (
                <li key={item.id}>
                  <h2>
                    {item.name} <small>{item.id}</small>
                  </h2>
                  <p>
                    {{
                      ingredient: "Raw Ingredients",
                      consumable: "Disposable Supplies",
                      reusable: "Reusable Containers",
                      equipment: "Equipment",
                      other: "Other Supplies",
                    }[item.category] || item.category}{" "}
                    ·{" "}
                    {item.container_type
                      ? materialNames[item.container_type]
                      : ""}{" "}
                    · Available: {item.available ?? "Unknown"} {item.unit}
                  </p>
                  {item.storage_location && (
                    <p>Storage: {item.storage_location}</p>
                  )}
                  {item.notes && <p>{item.notes}</p>}
                  {item.status === "archived" && (
                    <p>
                      Closed source: quantity is its last recorded balance, not
                      usable stock.
                    </p>
                  )}
                  {item.physical_id || item.spore_id ? (
                    <Link
                      to={`/culture-library/${item.physical_id ? "physical" : "spores"}/${item.physical_id || item.spore_id}`}
                    >
                      Biological record {item.physical_id || item.spore_id}
                    </Link>
                  ) : null}
                  <div className="actions">
                    <button
                      onClick={() => {
                        setEditing(item);
                        setAdjust(null);
                        setOpen(false);
                      }}
                    >
                      Edit {item.name}
                    </button>
                    <button
                      onClick={() => {
                        setOpen(false);
                        setAdjust(item);
                      }}
                    >
                      Adjust Quantity · {item.name}
                    </button>
                    <Link to={`/inventory/transactions?item=${item.id}`}>
                      Transaction history
                    </Link>
                  </div>
                </li>
              ))}
          </ul>
        </>
      )}
    </>
  );
}
export function IngredientFields({
  stock,
  ingredients,
  onChange,
}: {
  stock: Stock[];
  ingredients: Ingredient[];
  onChange: (values: Ingredient[]) => void;
}) {
  const raw = stock.filter(
    (s) => s.category === "ingredient" && s.status === "active",
  );
  return (
    <fieldset>
      <legend>Actual ingredient quantities</legend>
      {ingredients.map((ingredient, i) => (
        <div className="ingredient-row" key={i}>
          <Field
            name={`ingredient_${i}`}
            label={`Ingredient ${i + 1}`}
            required
            values={{ [`ingredient_${i}`]: ingredient.item_id }}
            set={(_, id) => {
              const item = raw.find((s) => s.id === id);
              onChange(
                ingredients.map((v, j) =>
                  i === j ? { ...v, item_id: id, unit: item?.unit || "g" } : v,
                ),
              );
            }}
            options={{
              "": "Choose raw ingredient",
              ...Object.fromEntries(
                raw.map((s) => [
                  s.id,
                  `${s.name} · ${s.available ?? "Unknown"} ${s.unit}`,
                ]),
              ),
            }}
          />
          <Field
            name={`amount_${i}`}
            label={`Ingredient ${i + 1} quantity (${ingredient.unit})`}
            required
            type="number"
            values={{ [`amount_${i}`]: ingredient.quantity }}
            set={(_, x) =>
              onChange(
                ingredients.map((v, j) =>
                  i === j ? { ...v, quantity: x } : v,
                ),
              )
            }
          />
          <Field
            name={`unit_${i}`}
            label={`Ingredient ${i + 1} unit`}
            values={{ [`unit_${i}`]: ingredient.unit }}
            options={compatibleUnits(
              raw.find((s) => s.id === ingredient.item_id)?.unit ||
                ingredient.unit,
            )}
            set={(_, unit) =>
              onChange(
                ingredients.map((v, j) => (i === j ? { ...v, unit } : v)),
              )
            }
          />
          <button
            type="button"
            onClick={() => onChange(ingredients.filter((_, j) => j !== i))}
          >
            Remove ingredient {i + 1}
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={!raw.length}
        onClick={() =>
          onChange([...ingredients, { item_id: "", quantity: "", unit: "g" }])
        }
      >
        Add Ingredient
      </button>
      {!raw.length && (
        <p>
          No raw ingredients are configured.{" "}
          <Link to="/inventory/stock">Open ingredient stock</Link>.
        </p>
      )}
    </fieldset>
  );
}
export function ProcessingFields({
  values,
  set,
}: {
  values: Values;
  set: (name: string, value: string) => void;
}) {
  return (
    <fieldset>
      <legend>Optional processing details</legend>
      <Field
        name="method"
        label="Processing method"
        values={values}
        set={set}
        options={{
          "": "Not recorded",
          pressure_cooker: "Pressure cooker",
          instant_pot: "Instant Pot",
          pasteurization: "Pasteurization",
          custom: "Custom",
        }}
      />
      {["duration_minutes", "temperature_c", "pressure_psi"].map((name) => (
        <Field
          key={name}
          name={name}
          label={
            {
              duration_minutes: "Duration (minutes)",
              temperature_c: "Temperature (°C)",
              pressure_psi: "Pressure (psi)",
            }[name]!
          }
          type="number"
          values={values}
          set={set}
        />
      ))}
      <Field
        name="processing_notes"
        label="Processing notes / custom method details"
        type="textarea"
        values={values}
        set={set}
      />
    </fieldset>
  );
}
export function processingPayload(v: Values) {
  return {
    method: v.method || null,
    duration_minutes: v.duration_minutes ? Number(v.duration_minutes) : null,
    temperature_c: v.temperature_c || null,
    pressure_psi: v.pressure_psi || null,
    notes: v.processing_notes || null,
  };
}
export function FinishForm({
  path,
  onSaved,
}: {
  path: string;
  onSaved: () => void;
}) {
  const [v, setV] = useState<Values>({
    action: "complete",
    action_date: localToday(),
    reason: "",
    notes: "",
  });
  const command = useInventoryCommand();
  const set = (n: string, x: string) => setV({ ...v, [n]: x });
  async function submit(e: FormEvent) {
    e.preventDefault();
    const result = await command.send(path, {
      ...v,
      action_date: v.action_date || null,
      notes: v.notes || null,
    });
    if (result) onSaved();
  }
  return (
    <form className="library-form" onSubmit={submit}>
      <h3>Complete or Mark Failed</h3>
      <p>
        This preserves the record and releases a tracked reusable allocation
        exactly once. Ordinary transfers do not complete a donor plate.
      </p>
      <Field
        name="finish_action"
        label="Lifecycle action"
        values={Object.fromEntries(
          Object.entries(v).map(([k, x]) => [`finish_${k}`, x]),
        )}
        set={(n, x) => set(n.replace("finish_", ""), x)}
        options={{ complete: "Complete", failed: "Mark Failed" }}
      />
      <Field
        name="finish_action_date"
        label="Action date (optional)"
        type="date"
        values={Object.fromEntries(
          Object.entries(v).map(([k, x]) => [`finish_${k}`, x]),
        )}
        set={(n, x) => set(n.replace("finish_", ""), x)}
      />
      <Field
        name="finish_reason"
        label="Lifecycle reason"
        required
        type="textarea"
        values={Object.fromEntries(
          Object.entries(v).map(([k, x]) => [`finish_${k}`, x]),
        )}
        set={(n, x) => set(n.replace("finish_", ""), x)}
      />
      <Field
        name="finish_notes"
        label="Lifecycle notes"
        type="textarea"
        values={Object.fromEntries(
          Object.entries(v).map(([k, x]) => [`finish_${k}`, x]),
        )}
        set={(n, x) => set(n.replace("finish_", ""), x)}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <button disabled={command.busy}>Confirm Lifecycle Action</button>
    </form>
  );
}
export function PreparedPage() {
  const { data, error, reload } = useInventoryList<Prepared>("materials");
  const [selected, setSelected] = useState<string[]>([]);
  const location = useLocation();
  const command = useInventoryCommand();
  return (
    <>
      <InventoryNav />
      <PageHeader
        title="Prepared Materials"
        description="Previous prepared materials remain accessible. Complete their existing inoculation here, or create new inoculated material directly through Quick Create."
      />
      {location.state?.message && <p role="status">{location.state.message}</p>}
      <div className="actions">
        <Link className="button primary" to="/inventory/prepared/prepare">
          Prepare Materials
        </Link>
        <Link to="/inventory/prepared/inoculate">
          Inoculate Previous Materials
        </Link>
      </div>
      {!data ? (
        <Feedback error={error} retry={reload} />
      ) : (
        <>
          {data.some((row) => row.stage === "preparing") && (
            <div className="actions">
              <button
                disabled={command.busy || !selected.length}
                onClick={async () => {
                  if (await command.send("ready", { prepared_ids: selected })) {
                    setSelected([]);
                    reload();
                  }
                }}
              >
                Confirm Selected Ready to Inoculate
              </button>
              <span>{selected.length} legacy Preparing records selected</span>
            </div>
          )}
          {command.error && <p role="alert">{command.error}</p>}
          <ul className="record-list panel">
            {data.map((row) => (
              <li key={row.id}>
                {row.stage === "preparing" && (
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={selected.includes(row.id)}
                      onChange={() =>
                        setSelected(
                          selected.includes(row.id)
                            ? selected.filter((id) => id !== row.id)
                            : [...selected, row.id],
                        )
                      }
                    />
                    Select {row.id} for readiness confirmation
                  </label>
                )}
                <Link to={`/inventory/prepared/${row.id}`}>
                  {row.id} · {materialNames[row.material_type]}
                </Link>
                <p>
                  {stageName(row.stage)} · Batch {row.batch_id} · Use by{" "}
                  {row.use_by || "Unknown"}
                </p>
                {row.expired && (
                  <p className="provenance-warning">
                    Use-by date has passed; review suitability. No automatic
                    failure was applied.
                  </p>
                )}
                {row.physical_id || row.spawn_id ? (
                  <Link
                    to={`/culture-library/${row.physical_id ? "physical" : "spawn"}/${row.physical_id || row.spawn_id}`}
                  >
                    View biological record
                  </Link>
                ) : null}
              </li>
            ))}
            {!data.length && <li>No prepared materials yet.</li>}
          </ul>
        </>
      )}
    </>
  );
}
export function PreparedDetail() {
  const { code = "" } = useParams();
  const [row, setRow] = useState<Prepared | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const command = useInventoryCommand();
  const [name, setName] = useState("");
  const [establishedDate, setEstablishedDate] = useState("");
  const [establishing, setEstablishing] = useState(false);
  const reload = () => setRevision((v) => v + 1);
  useEffect(() => {
    let live = true;
    preparationApi<Prepared>(`materials/${code}`)
      .then((r) => {
        if (live) {
          setRow(r);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [code, revision]);
  async function establish(e: FormEvent) {
    e.preventDefault();
    if (!row?.source) return;
    setEstablishing(true);
    setError("");
    try {
      await provenanceApi(`spores/${row.source.id}/establish`, "POST", {
        prepared_id: row.id,
        name: name || null,
        origin_date: establishedDate || null,
      });
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to establish culture");
    } finally {
      setEstablishing(false);
    }
  }
  return (
    <>
      <InventoryNav />
      <PageHeader
        title={code}
        description="Prepared material and immutable batch settings."
      />
      {error && (
        <p role="alert">
          {error}
          <button onClick={reload}>Reload material</button>
        </p>
      )}
      {row && row.id === code && (
        <>
          <section className="panel workflow-source">
            <h2>
              {materialNames[row.material_type]} · {stageName(row.stage)}
            </h2>
            <p>
              Batch {row.batch_id} · Prepared{" "}
              {row.snapshot.preparation_date || "date unknown"} · Use by{" "}
              {row.use_by || "unknown"}
            </p>
            {row.expired && (
              <p className="provenance-warning">
                Use-by date has passed. Review suitability; the record has not
                been automatically failed.
              </p>
            )}
            {row.snapshot.container_name && (
              <p>Container allocation: {row.snapshot.container_name}</p>
            )}
            <p>
              Recipe snapshot:{" "}
              {row.snapshot.recipe?.name || "Manual preparation"}
              {row.snapshot.recipe_revision != null
                ? ` · revision ${row.snapshot.recipe_revision}`
                : ""}
            </p>
            <h3>
              {row.snapshot.workflow === "direct"
                ? "Recipe amounts for this batch (no inventory deducted)"
                : "Actual ingredient use"}
            </h3>
            <ul>
              {row.snapshot.ingredients.map((i, index) => (
                <li key={i.item_id || index}>
                  {i.name || i.item_id}: {i.quantity} {i.unit}
                </li>
              ))}
            </ul>
            <h3>Processing snapshot</h3>
            <dl className="info-list">
              {Object.entries(row.snapshot.processing)
                .filter(([, v]) => v != null)
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>
                      {(
                        {
                          method: "Method",
                          duration_minutes: "Duration (minutes)",
                          temperature_c: "Temperature (°C)",
                          pressure_psi: "Pressure (psi)",
                          notes: "Processing notes",
                        } as Record<string, string>
                      )[k] || k}
                    </dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
            </dl>
            <p>{row.snapshot.recipe?.instructions}</p>
            <p>{row.snapshot.notes}</p>
            {row.source && (
              <p>
                Exact physical source:{" "}
                <Link
                  to={`/culture-library/${row.source.kind}/${row.source.id}`}
                >
                  {row.source.id}
                </Link>{" "}
                · {row.source.date || "Date unknown"} · Usage{" "}
                {row.source.usage_quantity ?? "Unknown"} {row.source.unit} ·{" "}
                {row.source.operation_id}
              </p>
            )}
            {row.physical_id || row.spawn_id ? (
              <Link
                className="button"
                to={`/culture-library/${row.physical_id ? "physical" : "spawn"}/${row.physical_id || row.spawn_id}`}
              >
                Open biological record & photographs
              </Link>
            ) : null}
            {row.stage === "preparing" && (
              <button
                disabled={command.busy}
                onClick={async () => {
                  if (await command.send("ready", { prepared_ids: [row.id] }))
                    reload();
                }}
              >
                Confirm Ready to Inoculate
              </button>
            )}
            {command.error && <p role="alert">{command.error}</p>}
          </section>
          {row.stage === "inoculated" &&
            row.source?.kind === "spores" &&
            !row.physical_id && (
              <form
                className="library-form panel workflow-form"
                onSubmit={establish}
              >
                <h2>Register Successful Establishment</h2>
                <p>
                  Only after a culture has established: create an independent
                  genetic line for this plate. Other plates from the same spores
                  are not assumed identical.
                </p>
                <label className="field">
                  <span>Established culture name (optional)</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Establishment date (optional)</span>
                  <input
                    type="date"
                    value={establishedDate}
                    onChange={(e) => setEstablishedDate(e.target.value)}
                  />
                </label>
                <button disabled={establishing}>
                  {establishing
                    ? "Registering…"
                    : "Register Successful Culture"}
                </button>
              </form>
            )}
          {!["completed", "failed"].includes(row.stage) && (
            <section className="panel workflow-source">
              <FinishForm
                path={`materials/${row.id}/finish`}
                onSaved={reload}
              />
            </section>
          )}
        </>
      )}
    </>
  );
}
export function TransactionsPage() {
  const [params] = useSearchParams();
  const audit = useInventoryList<{
    id: string;
    operation_type: string;
    created_at: string;
    payload: Record<string, unknown>;
  }>("operations");
  const { data, error, reload } = useInventoryList<Ledger>(
    `transactions${params.get("item") ? `?item_id=${encodeURIComponent(params.get("item")!)}` : ""}`,
  );
  return (
    <>
      <InventoryNav />
      <PageHeader
        title="Inventory Transactions"
        description="Append-only stock history. Unknown before/after quantities stay unknown; recorded usage is not an invented balance."
      />
      {!data ? (
        <Feedback error={error} retry={reload} />
      ) : (
        <ul className="record-list panel">
          {data.map((t) => (
            <li key={t.id}>
              <h2>
                {t.item_id} · {t.entry_type}
              </h2>
              <p>
                {t.amount ?? "Unmeasured"} {t.unit} ·{" "}
                {t.before_quantity ?? "Unknown"} →{" "}
                {t.after_quantity ?? "Unknown"}
              </p>
              <p>{t.reason}</p>
              <small>
                {t.operation_id} · {new Date(t.created_at).toLocaleString()}
              </small>
            </li>
          ))}
          {!data.length && <li>No inventory transactions yet.</li>}
        </ul>
      )}
      {audit.data && (
        <section className="panel workflow-source">
          <h2>Recent Operation Sessions</h2>
          <p>
            Latest 100 sessions. Reasons, dates and notes are retained without
            rewriting prior operations.
          </p>
          <ul className="record-list">
            {audit.data
              .filter(
                (op) =>
                  !params.get("item") ||
                  data?.some((t) => t.operation_id === op.id),
              )
              .slice(0, 100)
              .map((op) => (
                <li key={op.id}>
                  <h3>
                    {(
                      {
                        stock_opening: "Opening stock",
                        stock_adjust: "Stock adjustment",
                        recipe_create: "Recipe creation",
                        recipe_edit: "Recipe revision",
                        prepare: "Preparation",
                        ready: "Ready to Inoculate confirmation",
                        inoculate: "Inoculation / transfer",
                        finish_prepared: "Completion / failure",
                        finish_record: "Completion / failure",
                      } as Record<string, string>
                    )[op.operation_type.split(":")[0]] ||
                      op.operation_type}{" "}
                    · {op.id}
                  </h3>
                  <p>
                    {String(
                      op.payload.action_date ||
                        op.payload.inoculation_date ||
                        op.payload.preparation_date ||
                        op.created_at,
                    )}
                  </p>
                  {op.payload.reason ? (
                    <p>{String(op.payload.reason)}</p>
                  ) : null}
                  {op.payload.notes ? <p>{String(op.payload.notes)}</p> : null}
                  {Array.isArray(op.payload.prepared_ids) && (
                    <p>Containers: {op.payload.prepared_ids.join(", ")}</p>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
      {audit.error && (
        <p role="alert">
          {audit.error}
          <button onClick={audit.reload}>Reload operation history</button>
        </p>
      )}
    </>
  );
}

export function PoolOverview() {
  const pools = useInventoryList<Pool>("pools");
  if (!pools.data) return <Feedback error={pools.error} retry={pools.reload} />;
  if (!pools.data.length) return null;
  return (
    <section className="panel workflow-source pool-overview">
      <h2>Reusable Container Pools</h2>
      <p>
        Empty containers exclude every live reservation. Prepared and active
        records keep their permanent IDs when equipment is returned.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Pool</th>
              <th>Available Empty Containers</th>
              <th>Prepared and ready</th>
              <th>Active Cultures / Spawn</th>
              <th>Legacy Preparing</th>
              <th>Other reserved</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {pools.data.map((pool) => (
              <tr key={pool.item_id}>
                <th>{pool.name}</th>
                <td>{pool.available}</td>
                <td>{pool.ready}</td>
                <td>{pool.inoculated}</td>
                <td>{pool.preparing}</td>
                <td>{pool.other_reserved}</td>
                <td>{pool.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Link to="/inventory/prepared">
        View prepared materials and historical batches
      </Link>
    </section>
  );
}
