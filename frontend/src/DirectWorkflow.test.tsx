import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  RecipesHome,
  RecipeList,
  RecipeDetail,
  RecipeEditor,
  LCMediaPage,
} from "./pages/Recipes";
import DirectCreate from "./pages/DirectCreate";
import Growing from "./pages/Growing";
import { localToday } from "./libraryApi";
import type { LibraryRecord } from "./libraryApi";
import type { Recipe } from "./preparationApi";
const processing = {
  method: null,
  duration_minutes: null,
  temperature_c: null,
  pressure_psi: null,
  notes: null,
};
const formula = {
  id: "RCP-1",
  name: "Standard Agar",
  recipe_type: "agar",
  description: "Balanced nutrients",
  batch_yield: 5,
  ingredients: [{ item_id: "", name: "Agar", quantity: "10", unit: "g" }],
  instructions: "Sterilize",
  notes: "Trial",
  processing,
  status: "active",
  revision: 1,
  used: false,
  created_at: "2026-01-01",
  updated_at: "2026-01-02",
} as Recipe;
const source = {
  id: "LC-0001",
  kind: "physical",
  status: "active",
  line_id: "CL-1",
  material_type: "lc_jar",
  remaining_quantity: null,
  remaining_unit: null,
} as LibraryRecord;
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}
function mock(recipes: Recipe[] = [formula]) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = new URL(String(input), "http://test").pathname;
      if (init?.method && init.method !== "GET") {
        if (path.endsWith("/duplicate"))
          return response(
            { ...formula, id: "RCP-2", name: "Standard Agar (copy)" },
            201,
          );
        if (path.endsWith("/create"))
          return response(
            {
              materials: [
                {
                  id: "AG-0011",
                  physical_id: "AG-0011",
                  physical_label: "P-01",
                },
                {
                  id: "AG-0012",
                  physical_id: "AG-0012",
                  physical_label: "P-02",
                },
              ],
            },
            201,
          );
        return response({ ...formula }, 201);
      }
      if (path.endsWith("/recipes")) return response(recipes);
      if (path.includes("/recipes/")) return response(recipes[0]);
      if (path.endsWith("/stock")) return response([]);
      return response([]);
    });
}
function mount(ui: React.ReactNode, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);
}
test("Recipes landing has exactly four category cards without seeded examples", () => {
  mount(<RecipesHome />);
  expect(screen.getAllByRole("link")).toHaveLength(4);
  for (const category of ["LC Media", "Agar", "Spawn Seed", "Substrate"])
    expect(
      screen.getByRole("heading", { name: category, level: 2 }),
    ).toBeInTheDocument();
  expect(screen.queryByText("Standard Agar")).not.toBeInTheDocument();
});
test.each([
  ["agar", "Agar Recipes", "agar"],
  ["spawn-seed", "Spawn Seed Recipes", "grain"],
  ["substrate", "Substrate Recipes", "substrate"],
] as const)(
  "%s list links to detail and Add Recipe",
  async (category, title, type) => {
    mock([{ ...formula, recipe_type: type }]);
    mount(<RecipeList category={category} />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: formula.name }),
    ).toHaveAttribute("href", "/recipes/detail/RCP-1");
    expect(screen.getByRole("link", { name: "Add Recipe" })).toHaveAttribute(
      "href",
      `/recipes/${category}/new`,
    );
  },
);
test("Spawn Seed lists grain recipes separately from LC Media", async () => {
  mock([
    { ...formula, name: "Grain", recipe_type: "grain" },
    { ...formula, id: "RCP-2", name: "Historical LC", recipe_type: "lc" },
  ]);
  mount(<RecipeList category="spawn-seed" />);
  expect(
    await screen.findByRole("link", { name: "Grain" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Historical LC" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Recipe subtype")).not.toBeInTheDocument();
});
test("recipe creation uses named ingredients without stock and retains editable notes", async () => {
  const fetch = mock();
  mount(<RecipeEditor category="substrate" />);
  const u = userEvent.setup();
  await u.type(screen.getByLabelText("Recipe name *"), "Oyster substrate");
  await u.type(screen.getByLabelText("Ingredient 1 name *"), "Coir");
  await u.type(screen.getByLabelText("Ingredient 1 quantity *"), "1");
  await u.selectOptions(screen.getByLabelText("Ingredient 1 unit"), "lb");
  await u.type(screen.getByLabelText("Recipe notes"), "Variant A");
  await u.click(screen.getByRole("button", { name: "Save Recipe" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    recipe_type: "substrate",
    notes: "Variant A",
    ingredients: [{ name: "Coir", quantity: "1", unit: "lb", item_id: null }],
  });
  expect(
    fetch.mock.calls.some(([input]) => String(input).includes("/stock")),
  ).toBe(false);
});
test("recipe detail confirms deletion only for unused recipes", async () => {
  const fetch = mock();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  mount(
    <Routes>
      <Route path="/recipes/detail/:code" element={<RecipeDetail />} />
    </Routes>,
    "/recipes/detail/RCP-1",
  );
  const del = await screen.findByRole("button", { name: "Delete Recipe" });
  expect(
    screen.getByText("Last updated:", { exact: false }),
  ).toBeInTheDocument();
  await userEvent.click(del);
  expect(confirm).toHaveBeenCalledOnce();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
    false,
  );
  confirm.mockReturnValue(true);
  await userEvent.click(del);
  expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
    true,
  );
});
test("used recipes offer Archive and duplication opens an editable copy", async () => {
  const fetch = mock([{ ...formula, used: true }]);
  mount(
    <Routes>
      <Route path="/recipes/detail/:code" element={<RecipeDetail />} />
      <Route path="/recipes/detail/:code/edit" element={<RecipeEditor />} />
    </Routes>,
    "/recipes/detail/RCP-1",
  );
  await screen.findByRole("button", { name: "Archive Recipe" });
  expect(
    screen.queryByRole("button", { name: "Delete Recipe" }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Duplicate Recipe" }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith("/duplicate") && init?.method === "POST",
      ),
    ).toBe(true),
  );
  expect(
    await screen.findByRole("heading", { name: "Edit Recipe" }),
  ).toBeInTheDocument();
});
test("Quick Create filters recipes, defaults local date, requires no inventory and displays all permanent IDs", async () => {
  const fetch = mock([
    formula,
    { ...formula, id: "RCP-2", name: "Grain only", recipe_type: "grain" },
    { ...formula, id: "RCP-3", name: "Archived", status: "archived" },
  ]);
  mount(
    <DirectCreate
      operation="agar-plate"
      source={source}
      sourceControl={<p>Selected source LC-0001</p>}
    />,
  );
  const u = userEvent.setup();
  await screen.findByRole("option", { name: "Standard Agar" });
  expect(
    screen.queryByRole("option", { name: "Grain only" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Archived" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Inoculation date *")).toHaveValue(localToday());
  expect(screen.queryByLabelText(/Reusable pool/)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Prepare Materials" }),
  ).not.toBeInTheDocument();
  await u.selectOptions(screen.getByLabelText("Agar recipe *"), formula.id);
  await u.clear(screen.getByLabelText("Number of containers *"));
  await u.type(screen.getByLabelText("Number of containers *"), "2");
  await u.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByText("P-01, P-02", { selector: "p" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open P-01" })).toHaveAttribute(
    "href",
    "/culture-library/physical/AG-0011",
  );
  expect(
    screen.getByRole("button", { name: "Copy Labels" }),
  ).toBeInTheDocument();
  const call = fetch.mock.calls.find(
    ([input, init]) =>
      String(input).endsWith("/create") && init?.method === "POST",
  )!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    recipe_id: formula.id,
    source_id: source.id,
    count: 2,
    inoculation_date: localToday(),
  });
  expect(
    fetch.mock.calls.some(([input]) => String(input).includes("/stock")),
  ).toBe(false);
});
test("spawn creation selects jar or bag with grain recipes and uses stable retry keys", async () => {
  const fetch = mock([{ ...formula, recipe_type: "grain" }]);
  mount(
    <DirectCreate
      operation="spawn"
      source={{ ...source, remaining_quantity: "100", remaining_unit: "mL" }}
      sourceControl={<p>Known LC source</p>}
    />,
  );
  const u = userEvent.setup();
  await screen.findByRole("option", { name: formula.name });
  await u.selectOptions(screen.getByLabelText("Material type"), "spawn_bag");
  await u.selectOptions(
    screen.getByLabelText("Spawn Seed recipe *"),
    formula.id,
  );
  await u.type(screen.getByLabelText("Source usage per container *"), "4");
  fetch.mockImplementationOnce(async () =>
    response({ detail: "Retry required" }, 409),
  );
  const button = screen.getByRole("button", { name: "Create Spawn bag" });
  await u.click(button);
  await screen.findByRole("alert");
  await u.click(button);
  const calls = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(calls).toHaveLength(2);
  const a = JSON.parse(calls[0][1]!.body as string),
    b = JSON.parse(calls[1][1]!.body as string);
  expect(a.request_key).toBe(b.request_key);
  expect(a).toMatchObject({
    material_type: "spawn_bag",
    usage_per_container: "4",
  });
});
test("Cultivation lists source, recipe, dates and filters completed spawn", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response([
      {
        ...source,
        id: "SJ-0001",
        kind: "spawn",
        material_type: "spawn_jar",
        stage: "colonizing",
        lifecycle: "active",
        created_at: "2026-01-01",
        cultivation: {
          source: { id: source.id, kind: "physical", date: "2026-01-02" },
          snapshot: { recipe: formula },
        },
      },
      {
        ...source,
        id: "SB-0001",
        kind: "spawn",
        material_type: "spawn_bag",
        lifecycle: "failed",
        created_at: "2026-01-01",
        cultivation: null,
      },
    ]),
  );
  mount(<Growing workspace="cultivation" />);
  expect(await screen.findByRole("link", { name: /SJ-0001/ })).toHaveAttribute(
    "href",
    "/culture-library/spawn/SJ-0001",
  );
  expect(
    screen.getByText("Recipe: Standard Agar", { exact: false }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /SB-0001/ }),
  ).not.toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByLabelText("Show records"),
    "failed",
  );
  expect(screen.getByRole("link", { name: /SB-0001/ })).toBeInTheDocument();
});

test("Create More starts a fresh operation while retries retain their key", async () => {
  const fetch = mock();
  mount(
    <DirectCreate
      operation="agar-plate"
      source={source}
      sourceControl={<p>Source selected</p>}
    />,
  );
  const u = userEvent.setup();
  await screen.findByRole("option", { name: formula.name });
  await u.selectOptions(screen.getByLabelText("Agar recipe *"), formula.id);
  await u.click(screen.getByRole("button", { name: "Create Agar plate" }));
  await u.click(await screen.findByRole("button", { name: "Create More" }));
  await u.click(screen.getByRole("button", { name: "Create Agar plate" }));
  const calls = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(calls).toHaveLength(2);
  expect(JSON.parse(calls[0][1]!.body as string).request_key).not.toBe(
    JSON.parse(calls[1][1]!.body as string).request_key,
  );
});

test("source changes use the current source's volume unit before submitting", async () => {
  const fetch = mock();
  const u = userEvent.setup();
  const view = mount(
    <DirectCreate
      operation="agar-plate"
      source={undefined}
      sourceControl={<p>Loading source</p>}
    />,
  );
  await screen.findByRole("option", { name: formula.name });
  view.rerender(
    <MemoryRouter>
      <DirectCreate
        operation="agar-plate"
        source={{ ...source, remaining_quantity: "100", remaining_unit: "mL" }}
        sourceControl={<p>Source loaded</p>}
      />
    </MemoryRouter>,
  );
  await u.selectOptions(screen.getByLabelText("Agar recipe *"), formula.id);
  await u.type(screen.getByLabelText("Source usage per container *"), "2");
  expect(screen.getByLabelText("Source usage unit")).toHaveValue("mL");
  await u.click(screen.getByRole("button", { name: "Create Agar plate" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    unit: "mL",
    usage_per_container: "2",
  });
});

test("editing a legacy ingredient unit makes it independent of optional stock", async () => {
  const fetch = mock([
    {
      ...formula,
      ingredients: [
        { item_id: "INV-1", name: "Agar", quantity: "10", unit: "g" },
      ],
    },
  ]);
  mount(
    <Routes>
      <Route path="/recipes/detail/:code/edit" element={<RecipeEditor />} />
    </Routes>,
    "/recipes/detail/RCP-1/edit",
  );
  const u = userEvent.setup();
  await screen.findByLabelText("Ingredient 1 unit");
  await u.selectOptions(screen.getByLabelText("Ingredient 1 unit"), "mL");
  await u.click(screen.getByRole("button", { name: "Save Recipe" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(JSON.parse(call[1]!.body as string).ingredients).toEqual([
    { item_id: null, name: "Agar", quantity: "10", unit: "mL" },
  ]);
});

test("LC containers automatically apply the default without a recipe selector", async () => {
  const media = {
    ...formula,
    id: "RCP-LC",
    name: "Default media",
    recipe_type: "lc",
    is_lc_default: true,
  };
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = String(input);
      if (init?.method === "POST")
        return response(
          { materials: [{ id: "LC-0011", physical_id: "LC-0011" }] },
          201,
        );
      if (path.endsWith("lc-default")) return response({ recipe: media });
      return response([]);
    });
  mount(
    <DirectCreate
      operation="lc-container"
      source={source}
      sourceControl={<p>LC source preselected</p>}
    />,
  );
  expect(
    await screen.findByText(/LC Media: Default media/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("combobox", { name: /recipe/i }),
  ).not.toBeInTheDocument();
  const u = userEvent.setup();
  await u.type(
    screen.getByLabelText(
      "Measured total volume per destination (mL, optional)",
    ),
    "100",
  );
  await u.click(
    screen.getByRole("button", { name: "Create LC container / jar" }),
  );
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    recipe_id: null,
    material_type: "lc_jar",
    source_id: source.id,
    destination_volume_ml: "100",
  });
  expect(
    fetch.mock.calls.some(([input]) => String(input).endsWith("/recipes")),
  ).toBe(false);
});
test("LC syringe has no media input or default setup requirement", async () => {
  const fetch = mock();
  mount(
    <DirectCreate
      operation="lc-syringe"
      source={source}
      sourceControl={<p>LC source preselected</p>}
    />,
  );
  expect(
    screen.queryByRole("combobox", { name: /recipe/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Set Up LC Media" }),
  ).not.toBeInTheDocument();
  const u = userEvent.setup();
  await u.type(screen.getByLabelText("Source usage per container *"), "5");
  await u.click(screen.getByRole("button", { name: "Create LC syringe" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    recipe_id: null,
    material_type: "lc_syringe",
    usage_per_container: "5",
  });
  expect(
    fetch.mock.calls.some(([input]) =>
      /lc-default|\/recipes$/.test(String(input)),
    ),
  ).toBe(false);
});
test("missing LC default gives one-time setup without inventing media", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    response({ recipe: null }),
  );
  mount(
    <DirectCreate
      operation="lc-container"
      source={source}
      sourceControl={<p>Source</p>}
    />,
  );
  expect(
    await screen.findByRole("link", { name: "Set Up LC Media" }),
  ).toHaveAttribute("href", "/recipes/lc-media");
  expect(
    screen.getByRole("button", { name: "Create LC container / jar" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("combobox", { name: /recipe/i }),
  ).not.toBeInTheDocument();
});
test("LC Media category opens the designated formula directly", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
    String(input).endsWith("lc-default")
      ? response({
          recipe: {
            ...formula,
            id: "RCP-LC",
            name: "Default Media",
            recipe_type: "lc",
            is_lc_default: true,
          },
        })
      : response({
          ...formula,
          id: "RCP-LC",
          name: "Default Media",
          recipe_type: "lc",
          is_lc_default: true,
        }),
  );
  mount(<LCMediaPage />);
  expect(
    await screen.findByRole("heading", { name: "Default Media", level: 1 }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Default LC Media · automatically used/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Manage LC Media definitions/ }),
  ).toHaveAttribute("href", "/recipes/lc-media/manage");
});
test("historical LC formulas can be explicitly designated as default", async () => {
  const media = { ...formula, name: "Existing LC", recipe_type: "lc" };
  const fetch = mock([media]);
  mount(
    <Routes>
      <Route path="/recipes/detail/:code" element={<RecipeDetail />} />
    </Routes>,
    "/recipes/detail/RCP-1",
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Use as Default LC Media" }),
  );
  const call = fetch.mock.calls.find(
    ([input, init]) =>
      String(input).endsWith("lc-default") && init?.method === "POST",
  )!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    recipe_id: formula.id,
    expected_revision: 1,
  });
});
