import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { PreparedDetail, FinishForm } from "./pages/PreparationInventory";
import {
  PreparationWorkflow,
  MaterialOperationPanel,
} from "./pages/PreparationWorkflow";
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
test("legacy Preparing readiness is an explicit action and expired preparation is a warning, not automatic failure", async () => {
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
test("Historical lifecycle starts unselected, requires a reason and sends the explicit lifecycle date and notes", async () => {
  const fetch = mocks();
  const saved = vi.fn();
  mount(<FinishForm path="materials/AG-0001/finish" onSaved={saved} />);
  const u = userEvent.setup();
  expect(screen.getByLabelText("Lifecycle action *")).toHaveValue("");
  await u.selectOptions(screen.getByLabelText("Lifecycle action *"), "failed");
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

test("historical prepared-material inoculation directs new creation to Quick Create", async () => {
  mocks({ materials: [] });
  mount(<PreparationWorkflow operation="agar-plate" source={source} />);
  expect(
    await screen.findByText("No prepared containers available."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Create new inoculated material/ }),
  ).toHaveAttribute("href", "/");
  expect(
    screen.queryByRole("button", { name: "Prepare Containers" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Saved recipe (optional)"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText(/Number of prepared containers/),
  ).not.toBeInTheDocument();
});
test("LC detail corrects measured Remaining Culture Material with reason and revision", async () => {
  const fetch = mocks({
    stocks: [
      {
        ...raw,
        id: "INV-LC",
        category: "source",
        unit: "mL",
        available: "25.000",
        revision: 3,
      },
    ],
  });
  mount(
    <MaterialOperationPanel
      record={{ ...source, stock_item_id: "INV-LC" }}
      onSaved={vi.fn()}
    />,
  );
  const u = userEvent.setup();
  await u.click(
    screen.getByRole("button", { name: "Correct Remaining Culture Material" }),
  );
  await u.type(
    screen.getByLabelText("Measured remaining quantity (blank = unknown)"),
    "0",
  );
  await u.type(
    screen.getByLabelText("Measurement correction reason *"),
    "Measured empty",
  );
  await u.click(screen.getByRole("button", { name: "Save Measured Balance" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(call[0]).toBe("/api/preparation/stock/INV-LC/adjust");
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    mode: "correct",
    quantity: "0",
    unit: "mL",
    expected_revision: 3,
    reason: "Measured empty",
  });
});
