import CollapsiblePanel from "../components/CollapsiblePanel";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "../components/UI";
import { Field } from "./LibraryForms";
import { ProcessingFields, processingPayload } from "./PreparationInventory";
import {
  preparationApi,
  useInventoryCommand,
  useInventoryList,
  stockUnits,
  useLCMediaDefault,
} from "../preparationApi";
import type { Recipe, Ingredient } from "../preparationApi";
export const recipeCategories = {
  "lc-media": { name: "LC Media", types: ["lc"] },
  agar: { name: "Agar", types: ["agar"] },
  "spawn-seed": { name: "Spawn Seed", types: ["grain"] },
  substrate: { name: "Substrate", types: ["substrate"] },
};
export const recipeCategory = (type: string) =>
  type === "lc"
    ? "lc-media"
    : type === "agar"
      ? "agar"
      : type === "substrate"
        ? "substrate"
        : "spawn-seed";
export const recipeTypeName = (type: string) =>
  ({
    agar: "Agar",
    grain: "Grain spawn",
    lc: "LC Media",
    substrate: "Substrate",
  })[type] || type;
export function RecipeNav() {
  return (
    <nav className="actions" aria-label="Recipe categories">
      <Link to="/recipes">Recipes</Link>
      {Object.entries(recipeCategories).map(([key, c]) => (
        <Link key={key} to={`/recipes/${key}`}>
          {c.name}
        </Link>
      ))}
    </nav>
  );
}
export function RecipesHome() {
  return (
    <>
      <PageHeader
        title="Recipes"
        description="Choose a recipe category to browse and manage your cultivation formulas."
      />
      <div className="quick-create-grid">
        {Object.entries(recipeCategories).map(([key, c]) => (
          <Link
            className="panel workflow-source"
            key={key}
            to={`/recipes/${key}`}
          >
            <h2>{c.name}</h2>
            <p>
              {key === "lc-media"
                ? "One designated default formulation for new LC containers"
                : key === "agar"
                  ? "Agar media formulations"
                  : key === "spawn-seed"
                    ? "Grain spawn formulations"
                    : "Substrate formulas for fruiting grows"}
            </p>
          </Link>
        ))}
      </div>
    </>
  );
}
export function RecipeList({
  category,
}: {
  category: keyof typeof recipeCategories;
}) {
  const recipes = useInventoryList<Recipe>("recipes");
  const [compare, setCompare] = useState<string[]>([]);
  const group = recipeCategories[category];
  const rows = (recipes.data || []).filter((r) =>
    group.types.includes(r.recipe_type),
  );
  const selected = rows.filter((r) => compare.includes(r.id));
  return (
    <>
      <RecipeNav />
      <PageHeader
        title={`${group.name} Recipes`}
        description="Browse formulations, open a recipe to edit or duplicate it, or select variants to compare."
      />
      <Link className="button primary" to={`/recipes/${category}/new`}>
        {category === "lc-media" ? "Set Up LC Media" : "Add Recipe"}
      </Link>
      {recipes.error && (
        <p role="alert">
          {recipes.error}
          <button onClick={recipes.reload}>Retry recipes</button>
        </p>
      )}
      {!recipes.data && !recipes.error && <p role="status">Loading recipes…</p>}
      {selected.length > 1 && (
        <section className="panel workflow-source">
          <h2>Recipe Comparison</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Recipe</th>
                  <th>Yield (containers)</th>
                  <th>Ingredients</th>
                </tr>
              </thead>
              <tbody>
                {selected.map((r) => (
                  <tr key={r.id}>
                    <th>{r.name}</th>
                    <td>{r.batch_yield}</td>
                    <td>
                      {r.ingredients.map((i, index) => (
                        <p key={index}>
                          {i.name || i.item_id}: {i.quantity}{" "}
                          {stockUnits[i.unit as keyof typeof stockUnits]}
                        </p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {recipes.data && !rows.length && <p>No recipes in this category yet.</p>}
      <ul className="record-list panel">
        {rows.map((r) => (
          <li key={r.id}>
            <h2>
              <Link to={`/recipes/detail/${r.id}`}>{r.name}</Link>
            </h2>
            <p>
              {r.description ||
                r.instructions?.split("\n")[0] ||
                `${recipeTypeName(r.recipe_type)} · Yield ${r.batch_yield} containers`}
            </p>
            <p>
              {recipeTypeName(r.recipe_type)}
              {r.status === "archived" ? " · Archived" : ""}
            </p>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={compare.includes(r.id)}
                onChange={() =>
                  setCompare(
                    compare.includes(r.id)
                      ? compare.filter((id) => id !== r.id)
                      : [...compare, r.id],
                  )
                }
              />
              Compare {r.name}
            </label>
          </li>
        ))}
      </ul>
    </>
  );
}
export function useRecipe(code?: string) {
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setRecipe(null);
    setError("");
    if (code)
      preparationApi<Recipe>(`recipes/${code}`)
        .then((r) => {
          if (live) setRecipe(r);
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    return () => {
      live = false;
    };
  }, [code, attempt]);
  return { recipe, error, reload: () => setAttempt((v) => v + 1) };
}
export function RecipeDetail({
  recipeCode,
  onChanged,
}: {
  recipeCode?: string;
  onChanged?: () => void;
}) {
  const { code } = useParams();
  const data = useRecipe(recipeCode || code);
  const command = useInventoryCommand();
  const navigate = useNavigate();
  const r = data.recipe;
  async function action(kind: "delete" | "duplicate" | "archive") {
    if (!r) return;
    if (
      kind === "delete" &&
      !window.confirm(`Permanently delete unused recipe “${r.name}”?`)
    )
      return;
    if (kind === "duplicate") {
      const copy = await command.send<Recipe>(`recipes/${r.id}/duplicate`, {
        expected_revision: r.revision,
      });
      if (copy) navigate(`/recipes/detail/${copy.id}/edit`);
    } else if (kind === "delete") {
      if (
        await command.send(
          `recipes/${r.id}`,
          { expected_revision: r.revision },
          "DELETE",
        )
      )
        navigate(`/recipes/${recipeCategory(r.recipe_type)}`);
    } else {
      if (
        await command.send(
          `recipes/${r.id}`,
          {
            ...r,
            id: undefined,
            updated_at: undefined,
            used: undefined,
            is_lc_default: undefined,
            created_at: undefined,
            revision: undefined,
            status: "archived",
            expected_revision: r.revision,
          },
          "PUT",
        )
      ) {
        data.reload();
        onChanged?.();
      }
    }
  }
  return (
    <>
      <RecipeNav />
      {data.error && (
        <p role="alert">
          {data.error}
          <button onClick={data.reload}>Retry recipe</button>
        </p>
      )}
      {!r ? (
        !data.error && <p role="status">Loading recipe…</p>
      ) : (
        <>
          <PageHeader
            title={r.name}
            description={`${recipeCategories[recipeCategory(r.recipe_type)].name} · ${recipeTypeName(r.recipe_type)}${r.status === "archived" ? " · Archived" : ""}`}
          />
          <section className="panel workflow-source">
            <p>{r.description}</p>
            <h2>Ingredients</h2>
            <ul>
              {r.ingredients.map((i, index) => (
                <li key={index}>
                  {i.name || i.item_id}: {i.quantity}{" "}
                  {stockUnits[i.unit as keyof typeof stockUnits]}
                </li>
              ))}
            </ul>
            <p>Yield: {r.batch_yield} containers</p>
            <h2>Preparation Instructions</h2>
            <p className="preserve-lines">{r.instructions || "Not recorded"}</p>
            <CollapsiblePanel
              title="Processing & secondary details"
              summary={`Revision ${r.revision}`}
              level={3}
            >
              <p>
                Processing: {r.processing.method || "Not recorded"} ·{" "}
                {r.processing.duration_minutes ?? "Unknown"} min ·{" "}
                {r.processing.temperature_c ?? "Unknown"} °C ·{" "}
                {r.processing.pressure_psi ?? "Unknown"} psi
              </p>
              <p>{r.processing.notes}</p>
              <h2>Notes</h2>
              <p>{r.notes || "None"}</p>
              <p>Created: {new Date(r.created_at || "").toLocaleString()}</p>
              <p>
                Last updated:{" "}
                {r.updated_at
                  ? new Date(r.updated_at).toLocaleString()
                  : `Not recorded (created ${new Date(r.created_at || "").toLocaleDateString()})`}
              </p>
            </CollapsiblePanel>
            <div className="actions">
              <Link
                className="button primary"
                to={`/recipes/detail/${r.id}/edit`}
              >
                Edit Recipe
              </Link>
              <button
                disabled={command.busy}
                onClick={() => action("duplicate")}
              >
                Duplicate Recipe
              </button>
              {r.status !== "archived" && (
                <button
                  disabled={command.busy}
                  onClick={() => action("archive")}
                >
                  Archive Recipe
                </button>
              )}
              {!r.used && !r.is_lc_default && (
                <button
                  className="danger"
                  disabled={command.busy}
                  onClick={() => action("delete")}
                >
                  Delete Recipe
                </button>
              )}
              {r.recipe_type === "lc" &&
                r.status === "active" &&
                !r.is_lc_default && (
                  <button
                    disabled={command.busy}
                    onClick={async () => {
                      if (
                        await command.send("lc-default", {
                          recipe_id: r.id,
                          expected_revision: r.revision,
                        })
                      )
                        navigate("/recipes/lc-media");
                    }}
                  >
                    Use as Default LC Media
                  </button>
                )}
              {r.is_lc_default && (
                <span>
                  Default LC Media · automatically used for new LC containers
                </span>
              )}
            </div>
            {r.used && (
              <p>
                Used recipes retain their historical links and snapshots.
                Archive hides them from new operations.
              </p>
            )}
            {command.error && <p role="alert">{command.error}</p>}
          </section>
        </>
      )}
    </>
  );
}
export function RecipeEditor({
  category,
}: {
  category?: keyof typeof recipeCategories;
}) {
  const { code } = useParams();
  const data = useRecipe(code);
  return (
    <>
      <RecipeNav />
      {code ? (
        data.recipe ? (
          <RecipeForm key={data.recipe.id} recipe={data.recipe} />
        ) : (
          <p role={data.error ? "alert" : "status"}>
            {data.error || "Loading recipe…"}
            {data.error && <button onClick={data.reload}>Retry recipe</button>}
          </p>
        )
      ) : (
        <RecipeForm key={category} category={category} />
      )}
    </>
  );
}
function RecipeForm({
  recipe,
  category = "agar",
}: {
  recipe?: Recipe;
  category?: keyof typeof recipeCategories;
}) {
  const navigate = useNavigate();
  const command = useInventoryCommand();
  const [v, setV] = useState<Record<string, string>>({
    name: recipe?.name || "",
    recipe_type: recipe?.recipe_type || recipeCategories[category].types[0],
    batch_yield: String(recipe?.batch_yield || 1),
    description: recipe?.description || "",
    notes: recipe?.notes || "",
    instructions: recipe?.instructions || "",
    method: recipe?.processing.method || "",
    duration_minutes: String(recipe?.processing.duration_minutes ?? ""),
    temperature_c: recipe?.processing.temperature_c || "",
    pressure_psi: recipe?.processing.pressure_psi || "",
    processing_notes: recipe?.processing.notes || "",
    shelf_life_days: String(recipe?.shelf_life_days ?? ""),
    status: recipe?.status || "active",
  });
  const [ingredients, setIngredients] = useState<Ingredient[]>(
    recipe?.ingredients || [{ name: "", item_id: "", quantity: "", unit: "g" }],
  );
  const set = (n: string, x: string) => setV({ ...v, [n]: x });
  async function save(e: FormEvent) {
    e.preventDefault();
    const r = await command.send<Recipe>(
      recipe ? `recipes/${recipe.id}` : "recipes",
      {
        name: v.name,
        recipe_type: v.recipe_type,
        description: v.description || null,
        notes: v.notes || null,
        batch_yield: Number(v.batch_yield),
        instructions: v.instructions || null,
        processing: processingPayload(v),
        shelf_life_days: v.shelf_life_days ? Number(v.shelf_life_days) : null,
        ingredients: ingredients.map((i) => ({
          ...i,
          item_id: i.item_id || null,
        })),
        ...(recipe
          ? { status: v.status, expected_revision: recipe.revision }
          : {}),
      },
      recipe ? "PUT" : "POST",
    );
    if (r) navigate(`/recipes/detail/${r.id}`);
  }
  const types = recipe
    ? [recipe.recipe_type]
    : recipeCategories[category].types;
  return (
    <>
      <PageHeader
        title={recipe ? "Edit Recipe" : "Add Recipe"}
        description="Record your formulation, ingredients and preparation instructions."
      />
      <form className="library-form panel workflow-form" onSubmit={save}>
        <Field name="name" label="Recipe name" required values={v} set={set} />
        <Field
          name="recipe_type"
          label="Recipe type"
          values={v}
          set={set}
          options={Object.fromEntries(types.map((t) => [t, recipeTypeName(t)]))}
        />
        <Field
          name="description"
          label="Short description"
          values={v}
          set={set}
        />
        <Field
          name="batch_yield"
          label="Yield (containers)"
          type="number"
          required
          values={v}
          set={set}
        />
        <fieldset>
          <legend>Ingredients</legend>
          {ingredients.map((ingredient, index) => (
            <div key={index} className="ingredient-row">
              <Field
                name={`name_${index}`}
                label={`Ingredient ${index + 1} name`}
                required
                values={{
                  [`name_${index}`]: ingredient.name || ingredient.item_id,
                }}
                set={(_, name) =>
                  setIngredients(
                    ingredients.map((i, j) =>
                      j === index ? { ...i, name, item_id: "" } : i,
                    ),
                  )
                }
              />
              <Field
                name={`quantity_${index}`}
                label={`Ingredient ${index + 1} quantity`}
                required
                type="number"
                values={{ [`quantity_${index}`]: ingredient.quantity }}
                set={(_, quantity) =>
                  setIngredients(
                    ingredients.map((i, j) =>
                      j === index ? { ...i, quantity } : i,
                    ),
                  )
                }
              />
              <Field
                name={`unit_${index}`}
                label={`Ingredient ${index + 1} unit`}
                values={{ [`unit_${index}`]: ingredient.unit }}
                options={stockUnits}
                set={(_, unit) =>
                  setIngredients(
                    ingredients.map((i, j) =>
                      j === index ? { ...i, unit, item_id: "" } : i,
                    ),
                  )
                }
              />
              <button
                type="button"
                onClick={() =>
                  setIngredients(ingredients.filter((_, j) => j !== index))
                }
              >
                Remove ingredient {index + 1}
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button"
            onClick={() =>
              setIngredients([
                ...ingredients,
                { name: "", item_id: "", quantity: "", unit: "g" },
              ])
            }
          >
            Add Ingredient
          </button>
        </fieldset>
        <Field
          name="instructions"
          label="Preparation instructions"
          type="textarea"
          values={v}
          set={set}
        />
        <CollapsiblePanel title="Processing details (optional)">
          <ProcessingFields values={v} set={set} />
        </CollapsiblePanel>
        <Field
          name="notes"
          label="Recipe notes"
          type="textarea"
          values={v}
          set={set}
        />
        <Field
          name="shelf_life_days"
          label="Recommended shelf life (days)"
          type="number"
          values={v}
          set={set}
        />
        {recipe?.status === "archived" && (
          <Field
            name="status"
            label="Recipe status"
            values={v}
            set={set}
            options={{ active: "Active", archived: "Archived" }}
          />
        )}
        {command.error && <p role="alert">{command.error}</p>}
        <div className="actions">
          <button
            className="primary"
            disabled={command.busy || !ingredients.length}
          >
            Save Recipe
          </button>
          <Link
            to={
              recipe ? `/recipes/detail/${recipe.id}` : `/recipes/${category}`
            }
          >
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

export function LCMediaPage() {
  const media = useLCMediaDefault();
  if (media.error)
    return (
      <p role="alert">
        {media.error}
        <button onClick={media.reload}>Retry LC Media</button>
      </p>
    );
  if (media.data === undefined) return <p role="status">Loading LC Media…</p>;
  return media.data ? (
    <>
      <div className="actions">
        <Link to="/recipes/lc-media/manage">
          Manage LC Media definitions / change default
        </Link>
      </div>
      <RecipeDetail recipeCode={media.data.id} onChanged={media.reload} />
    </>
  ) : (
    <>
      <section className="panel workflow-source">
        <h2>Set Up LC Media</h2>
        <p>
          Define your formula once, then designate it as the default. Existing
          LC recipes are preserved below; open one to make it the default. No
          formulation is supplied automatically.
        </p>
      </section>
      <RecipeList category="lc-media" />
    </>
  );
}
