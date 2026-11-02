import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { Field } from "./LibraryForms";
import { localToday } from "../libraryApi";
import type { LibraryRecord } from "../libraryApi";
import {
  compatibleUnits,
  materialNames,
  scaleQuantity,
  stockUnits,
  useInventoryCommand,
  useInventoryList,
} from "../preparationApi";
import type { Prepared, Recipe } from "../preparationApi";
export default function DirectCreate({
  operation,
  source,
  sourceControl,
  onCreated,
}: {
  operation: string;
  source?: LibraryRecord;
  sourceControl: ReactNode;
  onCreated?: () => void;
}) {
  const recipes = useInventoryList<Recipe>("recipes");
  const command = useInventoryCommand();
  const first =
    {
      "agar-plate": "agar_plate",
      "lc-container": "lc_jar",
      "lc-syringe": "lc_syringe",
      spawn: "spawn_jar",
    }[operation] || "agar_plate";
  const [v, setV] = useState<Record<string, string>>({
    material_type: first,
    recipe_id: "",
    count: "1",
    inoculation_date: localToday(),
    usage_per_container: "",
    unit: "mL",
    unit_source: "",
    destination_volume_ml: "",
    notes: "",
  });
  const [result, setResult] = useState<Prepared[] | null>(null);
  const [copied, setCopied] = useState("");
  const liquid = source?.material_type?.startsWith("lc_");
  const type =
    v.material_type === "agar_plate"
      ? "agar"
      : v.material_type.startsWith("spawn_")
        ? "grain"
        : "lc";
  const allowed = (recipes.data || []).filter(
    (r) => r.status === "active" && r.recipe_type === type,
  );
  const usageUnits = liquid
    ? compatibleUnits("mL")
    : source?.remaining_unit
      ? compatibleUnits(source.remaining_unit)
      : stockUnits;
  const defaultUnit =
    source?.remaining_unit ||
    (liquid || source?.material_type === "spore_syringe"
      ? "mL"
      : source?.material_type === "agar_plate"
        ? "plate"
        : source?.unit || "count");
  const usageUnit =
    v.unit_source === source?.id && Object.hasOwn(usageUnits, v.unit)
      ? v.unit
      : Object.hasOwn(usageUnits, defaultUnit)
        ? defaultUnit
        : Object.keys(usageUnits)[0];
  const set = (n: string, x: string) =>
    setV({
      ...v,
      [n]: x,
      ...(n === "unit" ? { unit_source: source?.id || "" } : {}),
    });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!source) return;
    const r = await command.send<{ materials: Prepared[] }>("create", {
      material_type: v.material_type,
      recipe_id: v.recipe_id || null,
      source_kind: source.kind,
      source_id: source.id,
      count: Number(v.count),
      inoculation_date: v.inoculation_date,
      usage_per_container: v.usage_per_container || null,
      unit: usageUnit,
      destination_volume_ml: v.destination_volume_ml || null,
      notes: v.notes || null,
    });
    if (r) {
      setResult(r.materials);
      onCreated?.();
    }
  }
  if (result)
    return (
      <section className="panel workflow-source">
        <h2>
          Created {result.length} {result.length === 1 ? "record" : "records"}
        </h2>
        <p>Write these permanent IDs on your containers.</p>
        <p className="generated-ids">{result.map((r) => r.id).join(", ")}</p>
        <ul>
          {result.map((r) => (
            <li key={r.id}>
              <Link
                to={
                  r.physical_id || r.spawn_id
                    ? `/culture-library/${r.physical_id ? "physical" : "spawn"}/${r.id}`
                    : `/inventory/prepared/${r.id}`
                }
              >
                Open {r.id}
              </Link>
              {!r.physical_id &&
                !r.spawn_id &&
                " · Pending independent spore establishment"}
            </li>
          ))}
        </ul>
        <div className="actions">
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(
                  result.map((r) => r.id).join(", "),
                );
                setCopied("IDs copied.");
              } catch {
                setCopied("Copy the IDs from the selectable text below.");
              }
            }}
          >
            Copy IDs
          </button>
          <Link to={first.startsWith("spawn") ? "/cultivation" : "/laboratory"}>
            View growing records
          </Link>
          <button
            onClick={() => {
              command.reset();
              setResult(null);
              setCopied("");
            }}
          >
            Create More
          </button>
        </div>
        {copied && <p role="status">{copied}</p>}
        <label className="field">
          <span>Generated IDs for copying</span>
          <textarea
            aria-label="Generated IDs for copying"
            readOnly
            value={result.map((r) => r.id).join(", ")}
            onFocus={(e) => e.target.select()}
          />
        </label>
      </section>
    );
  return (
    <form className="library-form panel workflow-form" onSubmit={save}>
      <h2>Create inoculated material</h2>
      <p>
        Save after preparation, sterilization and inoculation are complete.
        Every container gets its own permanent ID. No container or ingredient
        inventory is required.
      </p>
      {operation === "spawn" && (
        <Field
          name="material_type"
          label="Material type"
          values={v}
          set={set}
          options={{ spawn_jar: "Spawn Jar", spawn_bag: "Spawn Bag" }}
        />
      )}
      <Field
        name="recipe_id"
        label={
          type === "agar"
            ? "Agar recipe"
            : type === "grain"
              ? "Spawn Seed recipe"
              : "LC media recipe"
        }
        required={v.material_type !== "lc_syringe"}
        values={v}
        set={set}
        options={{
          "":
            v.material_type === "lc_syringe"
              ? "No media recipe — filling from existing LC"
              : "Choose an active recipe",
          ...Object.fromEntries(allowed.map((r) => [r.id, r.name])),
        }}
      />
      {recipes.error && (
        <p role="alert">
          {recipes.error}
          <button type="button" onClick={recipes.reload}>
            Retry recipes
          </button>
        </p>
      )}
      {recipes.data && !allowed.length && v.material_type !== "lc_syringe" && (
        <p>
          No matching active recipes.{" "}
          <Link to={`/recipes/${type === "agar" ? "agar" : "spawn-seed"}`}>
            Add Recipe
          </Link>
        </p>
      )}
      {sourceControl}
      <Field
        name="count"
        label="Number of containers"
        type="number"
        required
        values={v}
        set={set}
      />
      <Field
        name="inoculation_date"
        label="Inoculation date"
        type="date"
        required
        values={v}
        set={set}
      />
      <Field
        name="usage_per_container"
        label="Source usage per container"
        type="number"
        required={
          source?.remaining_quantity != null || v.material_type === "lc_syringe"
        }
        values={v}
        set={set}
      />
      <Field
        name="unit"
        label="Source usage unit"
        values={{ ...v, unit: usageUnit }}
        set={set}
        options={usageUnits}
      />
      <p>
        Total source usage:{" "}
        {v.usage_per_container
          ? `${scaleQuantity(v.usage_per_container, Number(v.count))} ${usageUnit}`
          : "Unmeasured; unknown balances remain unknown"}
      </p>
      {source?.remaining_quantity != null && (
        <p>
          Remaining Culture Material: {source.remaining_quantity}{" "}
          {source.remaining_unit}
        </p>
      )}
      {v.material_type === "lc_jar" && (
        <Field
          name="destination_volume_ml"
          label="Measured total volume per destination (mL, optional)"
          type="number"
          values={v}
          set={set}
        />
      )}
      {source?.kind === "spores" && (
        <p>
          Each plate remains a pending independent establishment until you
          register a successful culture. No shared genetic line is assumed.
        </p>
      )}
      <Field
        name="notes"
        label="Cultivation notes"
        type="textarea"
        values={v}
        set={set}
      />
      {command.error && <p role="alert">{command.error}</p>}
      <div className="actions">
        <button
          className="primary"
          disabled={
            command.busy ||
            !source ||
            (v.material_type !== "lc_syringe" &&
              !allowed.some((r) => r.id === v.recipe_id))
          }
        >
          {command.busy
            ? "Creating…"
            : `Create ${materialNames[v.material_type]}`}
        </button>
      </div>
    </form>
  );
}
