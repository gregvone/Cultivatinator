import { verifyAgarSource } from "../quickCreate";
import { cultivationStatus } from "../containerApi";
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
  compatibleUnits,
} from "../preparationApi";
import type { Stock, Recipe, Prepared, Ingredient } from "../preparationApi";
import {
  IngredientFields,
  ProcessingFields,
  processingPayload,
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
  return (
    <section className="preparation-workflow">
      <InoculationForm operation={operation} source={source} />
    </section>
  );
}
export function PreparationForm() {
  const stock = useInventoryList<Stock>("stock");
  const recipes = useInventoryList<Recipe>("recipes");
  const command = useInventoryCommand();
  const navigate = useNavigate();
  const types = [
    "agar_plate",
    "spawn_jar",
    "spawn_bag",
    "lc_jar",
    "lc_syringe",
  ];
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
      navigate("/history/materials", {
        state: {
          message: `${r.materials.length} containers prepared and Ready to Inoculate.`,
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
        Ready to Inoculate records. Save after preparation and sterilization are
        complete.
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
export function InoculationForm({
  operation,
  source,
}: {
  operation: string;
  source?: LibraryRecord;
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
    if (!source || command.busy) return;
    const r = await command.send<{ materials: Prepared[] }>(
      "inoculate",
      {
        prepared_ids: actualIds,
        source_kind: source.kind,
        source_id: source.id,
        usage_per_container: v.usage_per_container || null,
        unit: v.unit,
        inoculation_date: v.inoculation_date || null,
        destination_volume_ml: v.destination_volume_ml || null,
        notes: v.notes || null,
      },
      "POST",
      () => verifyAgarSource(source, operation),
    );
    if (r)
      navigate("/history/materials", {
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
          Source {source.id} · Remaining Culture Material{" "}
          {source.remaining_quantity ?? "Unknown"} {source.remaining_unit || ""}
          . Starting acquisition quantities are not remaining balances.
        </p>
      )}
      <p>{allowed.length} prepared containers available.</p>
      {!allowed.length ? (
        <p>
          No prepared containers available.{" "}
          <Link to="/">Create new inoculated material from Quick Create</Link>
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
            ? compatibleUnits("mL")
            : source?.remaining_unit
              ? compatibleUnits(source.remaining_unit)
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
      <h2>Cultivation & Source History</h2>
      <p>
        Cultivation status: {cultivationStatus(record)} · Remaining Culture
        Material: {record.remaining_quantity ?? "Unknown"}{" "}
        {record.remaining_unit || ""}
      </p>
      <p>
        Balances are explicitly measured or remain unknown; initial registration
        quantities are preserved separately.
      </p>
      {record.kind === "physical" &&
        record.material_type?.startsWith("lc_") && (
          <CultureBalanceForm record={record} onSaved={onSaved} />
        )}
      {error && <p role="alert">{error}</p>}
      {history?.preparation?.snapshot.media_origin === "source_transfer" && (
        <p>
          Media transferred from{" "}
          <Link
            to={`/culture-library/physical/${history.preparation.snapshot.media_source_id}`}
          >
            {history.preparation.snapshot.media_source_id}
          </Link>
          .{" "}
          {history.preparation.snapshot.recipe
            ? "The original media formulation is retained below."
            : "The media formulation was not recorded for this source."}{" "}
          No new media preparation is recorded.
        </p>
      )}
      {history?.preparation?.snapshot.recipe && (
        <section>
          <h3>Recipe: {history.preparation.snapshot.recipe.name}</h3>
          {history.preparation.snapshot.media_origin === "source_transfer" && (
            <p>
              Inherited formulation yield:{" "}
              {history.preparation.snapshot.recipe.batch_yield} containers.
              Amounts below describe the original formula, not new preparation.
            </p>
          )}
          <p>
            Inoculated: {history.preparation.source?.date || "Not recorded"}
          </p>
          <p>{history.preparation.snapshot.recipe.instructions}</p>
          <ul>
            {(history.preparation.snapshot.media_origin === "source_transfer"
              ? history.preparation.snapshot.recipe.ingredients
              : history.preparation.snapshot.ingredients
            ).map((i, index) => (
              <li key={i.item_id || index}>
                {i.name || i.item_id}: {i.quantity} {i.unit}
              </li>
            ))}
          </ul>
          <p>{history.preparation.snapshot.notes}</p>
          {history.preparation.snapshot.recipe_id && (
            <Link
              to={`/recipes/detail/${history.preparation.snapshot.recipe_id}`}
            >
              Open recipe definition
            </Link>
          )}
        </section>
      )}
      {history?.preparation && (
        <p>
          <Link to={`/history/materials/${history.preparation.id}`}>
            {history.preparation.snapshot.workflow === "direct"
              ? "Recipe & source history"
              : "Previous preparation"}{" "}
            {history.preparation.id} · {history.preparation.batch_id}
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
                <Link to={`/history/materials/${row.id}`}>
                  {row.id} · {row.source?.operation_id}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function CultureBalanceForm({
  record,
  onSaved,
}: {
  record: LibraryRecord;
  onSaved: () => void;
}) {
  const stock = useInventoryList<Stock>("stock");
  const command = useInventoryCommand();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState<Values>({
    quantity: "",
    unit: record.remaining_unit || "mL",
    reason: "",
  });
  const item = stock.data?.find((s) => s.id === record.stock_item_id);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!stock.data || (record.stock_item_id && !item)) return;
    const result = item
      ? await command.send(`stock/${item.id}/adjust`, {
          mode: "correct",
          quantity: v.quantity || null,
          unit: v.unit,
          expected_revision: item.revision,
          reason: v.reason,
        })
      : await command.send("stock", {
          name: `Culture ${record.id}`,
          category: "source",
          source_kind: record.kind,
          source_id: record.id,
          unit: v.unit,
          available: v.quantity || null,
          reason: v.reason,
        });
    if (result) {
      setOpen(false);
      stock.reload();
      onSaved();
    }
  }
  if (!open)
    return (
      <button onClick={() => setOpen(true)}>
        Correct Remaining Culture Material
      </button>
    );
  return (
    <form className="library-form" onSubmit={submit}>
      <h3>Correct Remaining Culture Material</h3>
      <p>
        Enter a measured balance, or leave blank for Unknown. Include a reason;
        zero marks an LC source Depleted.
      </p>
      <Field
        name="culture_quantity"
        label="Measured remaining quantity (blank = unknown)"
        type="number"
        values={{ culture_quantity: v.quantity }}
        set={(_, x) => setV({ ...v, quantity: x })}
      />
      <Field
        name="culture_unit"
        label="Culture volume unit"
        values={{ culture_unit: v.unit }}
        set={(_, x) => setV({ ...v, unit: x })}
        options={compatibleUnits("mL")}
      />
      <Field
        name="culture_reason"
        label="Measurement correction reason"
        type="textarea"
        required
        values={{ culture_reason: v.reason }}
        set={(_, x) => setV({ ...v, reason: x })}
      />
      {(stock.error || command.error) && (
        <p role="alert">{stock.error || command.error}</p>
      )}
      {stock.error && (
        <button type="button" onClick={stock.reload}>
          Reload measured balance
        </button>
      )}
      <button
        disabled={
          command.busy || !stock.data || (!!record.stock_item_id && !item)
        }
      >
        Save Measured Balance
      </button>
      <button type="button" onClick={() => setOpen(false)}>
        Cancel
      </button>
    </form>
  );
}
