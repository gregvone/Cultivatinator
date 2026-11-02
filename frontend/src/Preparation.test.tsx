import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import {
  StockPage,
  RecipesPage,
  PreparedDetail,
  FinishForm,
} from "./pages/PreparationInventory";
import { PreparationWorkflow } from "./pages/PreparationWorkflow";
import { scaleQuantity, newRequestKey } from "./preparationApi";
import { quickCreate, eligibleSource } from "./quickCreate";
import type { Stock, Recipe, Prepared } from "./preparationApi";
import type { LibraryRecord } from "./libraryApi";
const raw = {
  id: "INV-1",
  name: "Raw ingredient",
  category: "ingredient",
  available: "1000.000",
  unit: "g",
  status: "active",
  revision: 1,
} as Stock;
const pool = {
  id: "INV-2",
  name: "LC jars",
  category: "reusable",
  available: "10.000",
  unit: "count",
  container_type: "lc_jar",
  status: "active",
  revision: 1,
} as Stock;
const processing = {
  method: null,
  duration_minutes: null,
  temperature_c: null,
  pressure_psi: null,
  notes: null,
};
const recipe = {
  id: "RCP-1",
  name: "LC recipe",
  recipe_type: "lc",
  batch_yield: 10,
  ingredients: [{ item_id: raw.id, quantity: "12.345", unit: "g" }],
  processing,
  shelf_life_days: 30,
  instructions: "Mix carefully",
  revision: 1,
  status: "active",
} as Recipe;
const source = {
  id: "LC-0001",
  kind: "physical",
  material_type: "lc_jar",
  status: "active",
  line_id: "CL-0001",
  remaining_quantity: "25.000",
  remaining_unit: "mL",
  lifecycle: "active",
} as LibraryRecord;
const prepared = Array.from({ length: 6 }, (_, i) => ({
  id: `SB-${String(i + 1).padStart(4, "0")}`,
  material_type: "spawn_bag",
  stage: "ready",
  batch_id: "PB-1",
  use_by: null,
  expired: false,
  physical_id: null,
  spawn_id: null,
  source: null,
  snapshot: {
    ingredients: [],
    processing,
    recipe: null,
    preparation_date: null,
    notes: null,
    container_name: "Bags",
  },
})) as Prepared[];
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}
function mocks({
  stocks = [raw, pool],
  recipes = [recipe],
  materials = prepared,
}: { stocks?: Stock[]; recipes?: Recipe[]; materials?: Prepared[] } = {}) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = new URL(String(input), "http://test").pathname;
      if (init?.method === "POST" || init?.method === "PUT")
        return response({ materials: materials.slice(0, 5) }, 201);
      if (path.endsWith("/stock")) return response(stocks);
      if (path.endsWith("/recipes")) return response(recipes);
      if (path.includes("/materials/")) return response(materials[0]);
      if (path.endsWith("/materials")) return response(materials);
      return response([]);
    });
}
function mount(ui: React.ReactNode, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}

test("quantity previews use exact integer thousandths and match server half-up scaling", () => {
  expect(scaleQuantity("0.1", 3)).toBe("0.300");
  expect(scaleQuantity("12.345", 5, 10)).toBe("6.173");
  expect(scaleQuantity("99999999999.999", 1)).toBe("99999999999.999");
  expect(scaleQuantity("invalid", 5)).toBe("");
});
test("opening reusable pools requires explicit user confirmation and creates no startup stock", async () => {
  const fetch = mocks({ stocks: [] });
  mount(<StockPage />);
  const u = userEvent.setup();
  await u.click(
    await screen.findByRole("button", { name: "Configure 20 Agar Plates" }),
  );
  expect(screen.getByLabelText("Confirmed free container count *")).toHaveValue(
    20,
  );
  expect(
    fetch.mock.calls.every(
      ([, init]) => !init?.method || init.method === "GET",
    ),
  ).toBe(true);
  await u.type(
    screen.getByLabelText("Opening balance reason *"),
    "Counted clean plates",
  );
  await u.click(screen.getByRole("button", { name: "Confirm Opening Stock" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      true,
    ),
  );
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    category: "reusable",
    container_type: "agar_plate",
    available: "20",
    reason: "Counted clean plates",
  });
});
test("recipe form records unit-bearing ingredient quantities and a declared container yield", async () => {
  const fetch = mocks({ recipes: [] });
  mount(<RecipesPage />);
  const u = userEvent.setup();
  await u.click(await screen.findByRole("button", { name: "New Recipe" }));
  await u.type(screen.getByLabelText("Recipe name *"), "Agar recipe");
  await u.clear(screen.getByLabelText("Recipe yield (containers) *"));
  await u.type(screen.getByLabelText("Recipe yield (containers) *"), "10");
  await u.click(screen.getByRole("button", { name: "Add Ingredient" }));
  await u.selectOptions(screen.getByLabelText("Ingredient 1 *"), raw.id);
  await u.type(screen.getByLabelText("Ingredient 1 quantity (g) *"), "12.345");
  await u.click(screen.getByRole("button", { name: "Save Recipe" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    batch_yield: 10,
    ingredients: [{ item_id: raw.id, quantity: "12.345", unit: "g" }],
  });
});
test("preparation scales a saved recipe and submits actual settings without any source requirement", async () => {
  const fetch = mocks();
  mount(<PreparationWorkflow operation="lc-container" />);
  const u = userEvent.setup();
  const count = await screen.findByLabelText(
    "Number of prepared containers (1–100) *",
  );
  await u.clear(count);
  await u.type(count, "5");
  await u.selectOptions(
    screen.getByLabelText("Reusable pool or disposable supply *"),
    pool.id,
  );
  await u.selectOptions(
    screen.getByLabelText("Saved recipe (optional)"),
    recipe.id,
  );
  expect(screen.getByLabelText("Ingredient 1 quantity (g) *")).toHaveValue(
    6.173,
  );
  await u.selectOptions(
    screen.getByLabelText("Processing method"),
    "instant_pot",
  );
  await u.click(screen.getByRole("button", { name: "Prepare Materials" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(call[0]).toBe("/api/preparation/prepare");
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    count: 5,
    material_type: "lc_jar",
    ingredients: [{ quantity: "6.173" }],
    processing: { method: "instant_pot" },
  });
});
test("partial bulk inoculation calculates 25mL, preserves source context and retries with the same idempotency key", async () => {
  const fetch = mocks();
  mount(<PreparationWorkflow operation="spawn" source={source} />);
  const u = userEvent.setup();
  await screen.findByText(
    "Choose ready containers (partial batches are supported)",
  );
  const checks = screen.getAllByRole("checkbox");
  for (const c of checks.slice(0, 5)) await u.click(c);
  await u.type(screen.getByLabelText("Source usage per container *"), "5");
  expect(screen.getByRole("status")).toHaveTextContent(
    "Selected: 5 · Total source requirement: 25.000 mL",
  );
  fetch.mockImplementationOnce(async () =>
    response({ detail: "Insufficient source volume" }, 409),
  );
  await u.click(
    screen.getByRole("button", { name: "Inoculate Selected Containers" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Insufficient source volume",
  );
  await u.click(
    screen.getByRole("button", { name: "Inoculate Selected Containers" }),
  );
  const calls = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(calls).toHaveLength(2);
  const a = JSON.parse(calls[0][1]!.body as string),
    b = JSON.parse(calls[1][1]!.body as string);
  expect(a.request_key).toBe(b.request_key);
  expect(a).toMatchObject({
    source_kind: "physical",
    source_id: source.id,
    prepared_ids: prepared.slice(0, 5).map((r) => r.id),
    usage_per_container: "5",
    unit: "mL",
  });
});
test("explicit balances and terminal lifecycle exclude sources while unknown legacy quantities remain eligible", () => {
  const op = quickCreate.find((op) => op.id === "lc-syringe")!;
  for (const lifecycle of ["depleted", "completed", "failed"])
    expect(eligibleSource(op, { ...source, lifecycle })).toBe(false);
  expect(
    eligibleSource(op, {
      ...source,
      remaining_quantity: null,
      quantity: "0.000",
    }),
  ).toBe(true);
  expect(
    eligibleSource(op, {
      ...source,
      remaining_quantity: "0.000",
      balance_tracked: true,
    }),
  ).toBe(false);
});
test("readiness is an explicit action and expired preparation is a warning, not automatic failure", async () => {
  const row = {
    ...prepared[0],
    stage: "preparing",
    expired: true,
    snapshot: {
      ...prepared[0].snapshot,
      recipe,
      ingredients: [
        {
          item_id: raw.id,
          name: "Historical ingredient",
          quantity: "6.173",
          unit: "g",
        },
      ],
    },
  };
  const fetch = mocks({ materials: [row] });
  // The detail route parameter is supplied through a small router in the actual application.
  const { Routes, Route } = await import("react-router-dom");
  mount(
    <Routes>
      <Route path="/inventory/prepared/:code" element={<PreparedDetail />} />
    </Routes>,
    "/inventory/prepared/SB-0001",
  );
  const button = await screen.findByRole("button", {
    name: "Confirm Ready to Inoculate",
  });
  expect(screen.getByText(/Use-by date has passed/)).toBeInTheDocument();
  expect(
    screen.getByText("Historical ingredient: 6.173 g"),
  ).toBeInTheDocument();
  expect(screen.getByText("Mix carefully")).toBeInTheDocument();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
    false,
  );
  await userEvent.click(button);
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(call[0]).toBe("/api/preparation/ready");
  expect(JSON.parse(call[1]!.body as string).prepared_ids).toEqual([row.id]);
});
test("Complete/Failed requires a reason and sends the explicit lifecycle date and notes", async () => {
  const fetch = mocks();
  const saved = vi.fn();
  mount(<FinishForm path="materials/AG-0001/finish" onSaved={saved} />);
  const u = userEvent.setup();
  await u.selectOptions(screen.getByLabelText("Lifecycle action"), "failed");
  await u.type(screen.getByLabelText("Lifecycle reason *"), "Contamination");
  await u.type(
    screen.getByLabelText("Lifecycle notes"),
    "Photograph attached to record",
  );
  await u.click(
    screen.getByRole("button", { name: "Confirm Lifecycle Action" }),
  );
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    action: "failed",
    reason: "Contamination",
    notes: "Photograph attached to record",
  });
  expect(saved).toHaveBeenCalledOnce();
});

test("idempotency keys support private-network HTTP without randomUUID", () => {
  const random = {
    getRandomValues: (buffer: Uint8Array) => buffer.fill(1),
  } as unknown as Crypto;
  expect(newRequestKey(random)).toBe("01".repeat(16));
});
