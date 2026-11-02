import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Field } from "./LibraryForms";
import { localToday } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import {
  preparationApi,
  useInventoryList,
  useInventoryCommand,
  materialNames,
  scaleQuantity,
  stockUnits,
} from "../preparationApi";
import type { Stock, Recipe, Prepared, Ingredient } from "../preparationApi";
import {
  IngredientFields,
  ProcessingFields,
  processingPayload,
  FinishForm,
} from "./PreparationInventory";

type Values = Record<string, string>;
const kindForOperation: Record<string, string[]> = {
  "agar-plate": ["agar_plate"],
  "lc-container": ["lc_jar"],
  "lc-syringe": ["lc_syringe"],
  spawn: ["spawn_jar", "spawn_bag"],
};
export function PreparationWorkflow({
  operation,
  source,
}: {
  operation: string;
  source?: LibraryRecord;
}) {
  const [mode, setMode] = useState(source ? "inoculate" : "prepare");
  return (
    <section className="preparation-workflow">
      <div
        className="library-tabs"
        role="group"
        aria-label="Preparation or inoculation"
      >
        <button
          aria-pressed={mode === "prepare"}
          onClick={() => setMode("prepare")}
        >
          Prepare Containers
        </button>
        <button
          aria-pressed={mode === "inoculate"}
          onClick={() => setMode("inoculate")}
        >
          {operation === "lc-syringe"
            ? "Fill Prepared Syringes"
            : "Inoculate Prepared Material"}
        </button>
      </div>
      {mode === "prepare" ? (
        <PreparationForm operation={operation} />
      ) : (
        <InoculationForm
          operation={operation}
          source={source}
          onPrepare={() => setMode("prepare")}
        />
      )}
    </section>
  );
}
function PreparationForm({ operation }: { operation: string }) {
  const stock = useInventoryList<Stock>("stock");
  const recipes = useInventoryList<Recipe>("recipes");
  const command = useInventoryCommand();
  const navigate = useNavigate();
  const types = kindForOperation[operation];
  const [v, setV] = useState<Values>({
    material_type: types[0],
    count: "1",
    container_item_id: "",
    recipe_id: "",
    preparation_date: localToday(),
    use_by: "",
    shelf_life_days: "",
    method: "",
    duration_minutes: "",
    temperature_c: "",
    pressure_psi: "",
    processing_notes: "",
    notes: "",
  });
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const compatible = (recipes.data || []).filter(
    (r) =>
      r.status === "active" &&
      r.recipe_type ===
        (v.material_type === "agar_plate"
          ? "agar"
          : v.material_type.startsWith("spawn")
            ? "grain"
            : "lc"),
  );
  function set(name: string, value: string) {
    const next = { ...v, [name]: value };
    if (name === "material_type") {
      next.container_item_id = "";
      next.recipe_id = "";
      setIngredients([]);
    }
    if (name === "recipe_id") {
      const recipe = compatible.find((r) => r.id === value);
      if (recipe) {
        setIngredients(
          recipe.ingredients.map((i) => ({
            ...i,
            quantity: scaleQuantity(
              i.quantity,
              Number(v.count),
              recipe.batch_yield,
            ),
          })),
        );
        Object.assign(next, {
          method: recipe.processing.method || "",
          duration_minutes: String(recipe.processing.duration_minutes ?? ""),
          temperature_c: recipe.processing.temperature_c || "",
          pressure_psi: recipe.processing.pressure_psi || "",
          processing_notes: recipe.processing.notes || "",
          shelf_life_days: String(recipe.shelf_life_days ?? ""),
        });
      } else setIngredients([]);
    }
    if (name === "count" && v.recipe_id) {
      const recipe = compatible.find((r) => r.id === v.recipe_id);
      if (recipe)
        setIngredients(
          recipe.ingredients.map((i) => ({
            ...i,
            quantity: scaleQuantity(
              i.quantity,
              Number(value),
              recipe.batch_yield,
            ),
          })),
        );
    }
    setV(next);
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await command.send<{ materials: Prepared[] }>("prepare", {
      material_type: v.material_type,
      count: Number(v.count),
      container_item_id: v.container_item_id,
      recipe_id: v.recipe_id || null,
      ingredients: v.material_type === "lc_syringe" ? [] : ingredients,
      preparation_date: v.preparation_date || null,
      processing: processingPayload(v),
      shelf_life_days: v.shelf_life_days ? Number(v.shelf_life_days) : null,
      ...(v.use_by ? { use_by: v.use_by } : {}),
      notes: v.notes || null,
    });
    if (r)
      navigate("/inventory/prepared", {
        state: {
          message: `${r.materials.length} containers prepared. Confirm readiness separately.`,
        },
      });
  }
  if (!stock.data || !recipes.data)
    return (
      <div className="feedback">
        {stock.error || recipes.error ? (
          <>
            <p role="alert">{stock.error || recipes.error}</p>
            <button
              onClick={() => {
                stock.reload();
                recipes.reload();
              }}
            >
              Retry preparation inventory
            </button>
          </>
        ) : (
          <p role="status">Loading preparation inventory…</p>
        )}
      </div>
    );
  const containers = stock.data.filter(
    (s) => s.status === "active" && s.container_type === v.material_type,
  );
  return (
    <form className="library-form panel workflow-form" onSubmit={submit}>
      <h2>Prepare {materialNames[v.material_type]}</h2>
      <p>
        Preparation deducts the actual ingredients and disposable supplies,
        reserves pooled reusable containers, and creates individually identified
        Preparing records. No inoculation or genetic line is implied.
      </p>
      {types.length > 1 && (
        <Field
          name="material_type"
          label="Preparation container type"
          values={v}
          set={set}
          options={Object.fromEntries(types.map((t) => [t, materialNames[t]]))}
        />
      )}
      <Field
        name="count"
        label="Number of prepared containers (1–100)"
        type="number"
        required
        values={v}
        set={set}
      />
      <Field
        name="container_item_id"
        label="Reusable pool or disposable supply"
        required
        values={v}
        set={set}
        options={{
          "": "Choose container inventory",
          ...Object.fromEntries(
            containers.map((s) => [
              s.id,
              `${s.name} · ${s.available ?? "Unknown"} available ${s.unit}`,
            ]),
          ),
        }}
      />
      {!containers.length && (
        <p className="provenance-warning">
          No matching container inventory.{" "}
          <Link to="/inventory/stock">Configure a pool or supply</Link> before
          preparation.
        </p>
      )}
      {v.material_type !== "lc_syringe" && (
        <>
          <Field
            name="recipe_id"
            label="Saved recipe (optional)"
            values={v}
            set={set}
            options={{
              "": "Enter actual quantities manually",
              ...Object.fromEntries(
                compatible.map((r) => [
                  r.id,
                  `${r.name} · yield ${r.batch_yield}`,
                ]),
              ),
            }}
          />
          {v.recipe_id && (
            <p>
              Scaled to {v.count} containers. Review or edit the actual
              quantities below; changing count recalculates the recipe amounts.
            </p>
          )}
          <IngredientFields
            stock={stock.data}
            ingredients={ingredients}
            onChange={setIngredients}
          />
        </>
      )}
      <Field
        name="preparation_date"
        label="Preparation date (optional)"
        type="date"
        values={v}
        set={set}
      />
      <ProcessingFields values={v} set={set} />
      <Field
        name="shelf_life_days"
        label="Shelf life (days, optional)"
        type="number"
        values={v}
        set={set}
      />
      <Field
        name="use_by"
        label="Use-by override (optional)"
        type="date"
        values={v}
        set={set}
      />
      <p>
        With a preparation date and shelf life, use-by is calculated unless
        overridden. Expiry warns; it never automatically discards a record.
      </p>
      <Field
        name="notes"
        label="Preparation session notes"
        type="textarea"
        values={v}
        set={set}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <button className="primary" disabled={command.busy || !containers.length}>
        {command.busy ? "Preparing…" : "Prepare Materials"}
      </button>
    </form>
  );
}
function InoculationForm({
  operation,
  source,
  onPrepare,
}: {
  operation: string;
  source?: LibraryRecord;
  onPrepare: () => void;
}) {
  const materials = useInventoryList<Prepared>("materials?stage=ready");
  const command = useInventoryCommand();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string[]>([]);
  const initialUnit =
    source?.remaining_unit ||
    (source?.material_type?.startsWith("lc_") ||
    source?.material_type === "spore_syringe"
      ? "mL"
      : source?.material_type === "agar_plate"
        ? "plate"
        : source?.unit || "count");
  const [v, setV] = useState<Values>({
    usage_per_container: "",
    unit: initialUnit,
    inoculation_date: localToday(),
    destination_volume_ml: "",
    notes: "",
  });
  useEffect(() => {
    setV((old) => ({ ...old, unit: initialUnit }));
  }, [initialUnit]);
  const allowed = (materials.data || []).filter(
    (r) =>
      r.stage === "ready" &&
      kindForOperation[operation].includes(r.material_type),
  );
  const actualIds = selected.filter((id) => allowed.some((r) => r.id === id));
  const total = v.usage_per_container
    ? scaleQuantity(v.usage_per_container, actualIds.length)
    : "Unmeasured";
  const liquid = source?.material_type?.startsWith("lc_");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!source) return;
    const r = await command.send<{ materials: Prepared[] }>("inoculate", {
      prepared_ids: actualIds,
      source_kind: source.kind,
      source_id: source.id,
      usage_per_container: v.usage_per_container || null,
      unit: v.unit,
      inoculation_date: v.inoculation_date || null,
      destination_volume_ml: v.destination_volume_ml || null,
      notes: v.notes || null,
    });
    if (r)
      navigate("/inventory/prepared", {
        state: {
          message: `${r.materials.length} containers inoculated or filled in one operation.`,
        },
      });
  }
  if (!materials.data)
    return (
      <div className="feedback">
        {materials.error ? (
          <>
            <p role="alert">{materials.error}</p>
            <button onClick={materials.reload}>Retry prepared materials</button>
          </>
        ) : (
          <p role="status">Loading ready materials…</p>
        )}
      </div>
    );
  return (
    <form className="library-form panel workflow-form" onSubmit={submit}>
      <h2>
        {operation === "lc-syringe"
          ? "Fill Prepared Syringes"
          : "Inoculate Prepared Material"}
      </h2>
      {!source ? (
        <p className="provenance-warning">
          Choose an eligible source above before inoculation.
        </p>
      ) : (
        <p>
          Source {source.id} · Remaining{" "}
          {source.remaining_quantity ?? "Unknown"} {source.remaining_unit || ""}
          . Starting acquisition quantities are not remaining balances.
        </p>
      )}
      {!allowed.length ? (
        <p>
          No matching Ready to Inoculate containers.{" "}
          <button type="button" onClick={onPrepare}>
            Prepare containers first
          </button>
          , then explicitly confirm readiness in Prepared Materials.
        </p>
      ) : (
        <fieldset>
          <legend>
            Choose ready containers (partial batches are supported)
          </legend>
          <button
            type="button"
            onClick={() => setSelected(allowed.slice(0, 100).map((r) => r.id))}
          >
            Select Up to 100 Ready Containers
          </button>
          {allowed.map((row) => (
            <label className="checkbox" key={row.id}>
              <input
                type="checkbox"
                checked={actualIds.includes(row.id)}
                onChange={() =>
                  setSelected(
                    actualIds.includes(row.id)
                      ? actualIds.filter((id) => id !== row.id)
                      : [...actualIds, row.id],
                  )
                }
              />
              {row.id} · {materialNames[row.material_type]} · {row.batch_id}
              {row.expired ? " · Use-by passed: review suitability" : ""}
            </label>
          ))}
        </fieldset>
      )}
      <Field
        name="usage_per_container"
        label="Source usage per container"
        type="number"
        required={!!liquid || source?.remaining_quantity != null}
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
      />
      <Field
        name="unit"
        label="Source usage unit"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
        options={
          liquid
            ? { mL: "mL" }
            : source?.remaining_unit
              ? { [source.remaining_unit]: source.remaining_unit }
              : stockUnits
        }
      />
      <p role="status">
        Selected: {actualIds.length} · Total source requirement: {total}{" "}
        {v.unit}
      </p>
      <p>
        Known stock is validated and deducted once. Unknown stock records usage
        without a fabricated balance. Donor plates remain active until
        explicitly completed or failed.
      </p>
      {operation === "lc-container" && (
        <Field
          name="destination_volume_ml"
          label="Measured total volume per destination (mL, optional)"
          type="number"
          values={v}
          set={(n, x) => setV({ ...v, [n]: x })}
        />
      )}
      {source?.kind === "spores" && (
        <p className="provenance-warning">
          Spore inoculation creates pending agar establishments, not shared
          genetic lines. Register each successful culture separately from its
          prepared record.
        </p>
      )}
      <Field
        name="inoculation_date"
        label="Inoculation / transfer date (optional)"
        type="date"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
      />
      <Field
        name="notes"
        label="Inoculation notes"
        type="textarea"
        values={v}
        set={(n, x) => setV({ ...v, [n]: x })}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <button
        className="primary"
        disabled={
          command.busy || !source || !actualIds.length || actualIds.length > 100
        }
      >
        {command.busy
          ? "Saving operation…"
          : operation === "lc-syringe"
            ? "Fill Selected Syringes"
            : "Inoculate Selected Containers"}
      </button>
    </form>
  );
}
export function MaterialOperationPanel({
  record,
  onSaved,
}: {
  record: LibraryRecord;
  onSaved: () => void;
}) {
  const [history, setHistory] = useState<{
    preparation: Prepared | null;
    destinations: Prepared[];
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    preparationApi<{ preparation: Prepared | null; destinations: Prepared[] }>(
      `records/${record.kind}/${record.id}`,
    )
      .then((v) => {
        if (live) setHistory(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [record]);
  if (!["physical", "spawn", "spores"].includes(record.kind)) return null;
  return (
    <section className="panel workflow-source">
      <h2>Lifecycle, Preparation & Physical Transfers</h2>
      <p>
        Lifecycle: {record.lifecycle || "active"} · Remaining:{" "}
        {record.remaining_quantity ?? "Unknown"} {record.remaining_unit || ""}
      </p>
      <p>
        Balances are explicitly measured or remain unknown; initial registration
        quantities are preserved separately.
      </p>
      {["physical", "spores"].includes(record.kind) && (
        <Link
          to={
            record.stock_item_id
              ? `/inventory/stock?item=${record.stock_item_id}`
              : `/inventory/stock?source_kind=${record.kind}&source_id=${record.id}`
          }
        >
          {record.stock_item_id
            ? "Adjust documented balance in Inventory"
            : "Configure explicit source balance"}
        </Link>
      )}
      {error && <p role="alert">{error}</p>}
      {history?.preparation && (
        <p>
          <Link to={`/inventory/prepared/${history.preparation.id}`}>
            Preparation {history.preparation.id} ·{" "}
            {history.preparation.batch_id}
          </Link>
          {history.preparation.source && (
            <>
              {" "}
              · Exact physical source:{" "}
              <Link
                to={`/culture-library/${history.preparation.source.kind}/${history.preparation.source.id}`}
              >
                {history.preparation.source.id}
              </Link>
            </>
          )}
        </p>
      )}
      {!!history?.destinations?.length && (
        <>
          <h3>Physical transfer destinations</h3>
          <ul>
            {history.destinations.map((row) => (
              <li key={row.id}>
                <Link to={`/inventory/prepared/${row.id}`}>
                  {row.id} · {row.source?.operation_id}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      {["physical", "spawn"].includes(record.kind) &&
        !["completed", "failed"].includes(record.lifecycle || "active") && (
          <FinishForm
            path={`records/${record.kind}/${record.id}/finish`}
            onSaved={onSaved}
          />
        )}
    </section>
  );
}
