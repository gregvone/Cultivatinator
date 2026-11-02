import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "./App";
import { quickCreate, availableOperations } from "./quickCreate";
import type { LibraryRecord } from "./libraryApi";
const base = {
  name: null,
  status: "active",
  strain_name: "Oyster",
  strain_id: "STR-0001",
  line_id: "CL-0001",
  created_at: "2026-01-01",
  quantity: null,
  unit: null,
};
const records = [
  { ...base, id: "AG-0001", kind: "physical", material_type: "agar_plate" },
  { ...base, id: "SL-0001", kind: "physical", material_type: "slant" },
  {
    ...base,
    id: "LC-0001",
    kind: "physical",
    material_type: "lc_jar",
    quantity: "0",
  },
  { ...base, id: "LC-0002", kind: "physical", material_type: "lc_syringe" },
  {
    ...base,
    id: "LC-archived",
    kind: "physical",
    material_type: "lc_jar",
    status: "archived",
  },
  { ...base, id: "PC-0001", kind: "physical", material_type: "other_culture" },
  {
    ...base,
    id: "SP-0001",
    kind: "spores",
    material_type: "spore_print",
    line_id: null,
  },
  {
    ...base,
    id: "SP-archived",
    kind: "spores",
    material_type: "spore_syringe",
    status: "archived",
  },
  {
    ...base,
    id: "SJ-0001",
    kind: "spawn",
    material_type: "spawn_jar",
    stage: "ready",
  },
  {
    ...base,
    id: "SB-0001",
    kind: "spawn",
    material_type: "spawn_bag",
    stage: "ready",
  },
  {
    ...base,
    id: "SJ-colonizing",
    kind: "spawn",
    material_type: "spawn_jar",
    stage: "colonizing",
  },
  {
    ...base,
    id: "SJ-used",
    kind: "spawn",
    material_type: "spawn_jar",
    stage: "used",
  },
  {
    ...base,
    id: "SJ-archived",
    kind: "spawn",
    material_type: "spawn_jar",
    stage: "ready",
    status: "archived",
  },
  {
    ...base,
    id: "FR-0001",
    kind: "fruiting",
    material_type: "bag",
    stage: "fruiting",
    line_id: null,
  },
  {
    ...base,
    id: "FR-archived",
    kind: "fruiting",
    material_type: "bag",
    status: "archived",
  },
] as LibraryRecord[];
const summary = {
  counts: {
    active_cultures: 0,
    spawn_containers: 0,
    fruiting_units: 0,
    open_alerts: 0,
  },
  attention_items: [],
  active_cultivation: [],
  recent_activity: [],
  environmental_observations: [],
};
function mock() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = new URL(String(input), "http://test").pathname;
    let data: unknown = [];
    if (path.endsWith("/summary")) data = summary;
    else if (path.startsWith("/api/preparation/records/"))
      data = { preparation: null, destinations: [] };
    else if (path.startsWith("/api/provenance/"))
      data = {
        origin_type: "external",
        ancestry_status: "unknown",
        revision: 1,
        parents: [],
        relationships: [],
        warnings: [],
      };
    else if (path.endsWith("/photos") || path.endsWith("/activity")) data = [];
    else if (path.startsWith("/api/library/")) {
      const [kind, id] = path.split("/").slice(3);
      data = id
        ? records.find((r) => r.kind === kind && r.id === id)
        : records.filter((r) => r.kind === kind);
    }
    return new Response(JSON.stringify(data ?? {}), { status: 200 });
  });
}
function Location() {
  const l = useLocation();
  return (
    <output aria-label="Current route">
      {l.pathname}
      {l.search}
    </output>
  );
}
function mount(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <Location />
    </MemoryRouter>,
  );
}
test("dashboard offers six dedicated workflow destinations", async () => {
  mock();
  mount();
  await screen.findByTestId("active_cultures");
  const panel = screen
    .getByRole("heading", { name: "Quick Create" })
    .closest("section")!;
  expect(within(panel).getAllByRole("link")).toHaveLength(6);
  for (const op of quickCreate)
    expect(within(panel).getByRole("link", { name: op.title })).toHaveAttribute(
      "href",
      `/quick-create/${op.id}`,
    );
});
test.each([
  [
    "agar-plate",
    [
      "physical:AG-0001",
      "physical:SL-0001",
      "physical:LC-0001",
      "physical:LC-0002",
      "spores:SP-0001",
    ],
  ],
  ["lc-syringe", ["physical:LC-0001", "physical:LC-0002"]],
  [
    "lc-container",
    [
      "physical:AG-0001",
      "physical:SL-0001",
      "physical:LC-0001",
      "physical:LC-0002",
    ],
  ],
  [
    "spawn",
    [
      "physical:AG-0001",
      "physical:SL-0001",
      "physical:LC-0001",
      "physical:LC-0002",
    ],
  ],
  ["spore-print", ["fruiting:FR-0001"]],
  ["fruiting-container", ["spawn:SJ-0001", "spawn:SB-0001"]],
])(
  "%s filters sources without treating quantities as balances",
  async (id, expected) => {
    const fetch = mock();
    mount(`/quick-create/${id}`);
    const select = await screen.findByRole("combobox", {
      name: "Source material",
    });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => (o as HTMLOptionElement).value)
        .filter(Boolean),
    ).toEqual(expected);
    if (id === "fruiting-container") {
      await userEvent.selectOptions(select, expected[0]);
      expect(
        screen.getByText("OPERATION NOT YET AVAILABLE"),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /save|create|register/i }),
      ).not.toBeInTheDocument();
    }
    expect(
      fetch.mock.calls.every(
        ([, init]) => !init?.method || init.method === "GET",
      ),
    ).toBe(true);
  },
);
test("Create From This carries an LC source into a matching destination", async () => {
  mock();
  mount("/culture-library/physical/LC-0001");
  const u = userEvent.setup();
  await u.click(await screen.findByText("Create From This"));
  const context = screen.getByRole("navigation", {
    name: "Create from LC-0001",
  });
  expect(
    within(context).queryByRole("link", { name: "New Fruiting Container" }),
  ).not.toBeInTheDocument();
  await u.click(within(context).getByRole("link", { name: "New LC Syringe" }));
  expect(
    await screen.findByRole("combobox", { name: "Source material" }),
  ).toHaveValue("physical:LC-0001");
  expect(
    screen.getByRole("option", { name: /LC-0001.*Oyster.*CL-0001.*active/ }),
  ).toBeInTheDocument();
});
test("ready spawn and fruiting context actions use the right source kinds", () => {
  expect(
    availableOperations(records.find((r) => r.id === "SJ-0001")!).map(
      (o) => o.id,
    ),
  ).toEqual(["fruiting-container"]);
  expect(
    availableOperations(records.find((r) => r.id === "FR-0001")!).map(
      (o) => o.id,
    ),
  ).toEqual(["spore-print"]);
  expect(
    availableOperations(records.find((r) => r.id === "SJ-colonizing")!),
  ).toEqual([]);
  expect(
    availableOperations(records.find((r) => r.id === "LC-archived")!),
  ).toEqual([]);
});
test.each([
  "physical:LC-archived",
  "spores:SP-0001",
  "spawn:SJ-colonizing",
  "physical:missing",
])("invalid syringe preselection %s is rejected", async (value) => {
  mock();
  const [kind, id] = value.split(":");
  mount(`/quick-create/lc-syringe?source_kind=${kind}&source_id=${id}`);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "unavailable or unsuitable",
  );
  expect(screen.getByRole("combobox", { name: "Source material" })).toHaveValue(
    "",
  );
});
test("source failures offer retry without exposing collection submit", async () => {
  const fetch = mock();
  fetch.mockRejectedValueOnce(new Error("Source load failed"));
  mount("/quick-create/spore-print?source_kind=fruiting&source_id=FR-0001");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Source load failed",
  );
  expect(
    screen.queryByRole("button", { name: "Register Spore Print" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Retry sources" }));
  expect(
    await screen.findByRole("button", { name: "Register Spore Print" }),
  ).toBeInTheDocument();
});
test("spore print uses collection endpoint and retains values on rejection", async () => {
  const fetch = mock();
  mount("/quick-create/spore-print?source_kind=fruiting&source_id=FR-0001");
  const button = await screen.findByRole("button", {
    name: "Register Spore Print",
  });
  await userEvent.type(
    screen.getByLabelText("Optional name"),
    "Collected print",
  );
  fetch.mockImplementationOnce(
    async () =>
      new Response(JSON.stringify({ detail: "Collection rejected" }), {
        status: 422,
      }),
  );
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Collection rejected",
  );
  expect(screen.getByLabelText("Optional name")).toHaveValue("Collected print");
  const writes = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(writes).toHaveLength(1);
  expect(writes[0][0]).toBe("/api/provenance/fruiting/FR-0001/collect");
  expect(JSON.parse(writes[0][1]!.body as string)).toMatchObject({
    material_type: "spore_print",
    name: "Collected print",
  });
});
test("Inventory owns acquisition and management while Culture Library stays clean", async () => {
  mock();
  mount("/culture-library");
  const u = userEvent.setup();
  await screen.findByRole("searchbox");
  for (const name of [
    "Receive Acquisition",
    "Receive Culture",
    "Receive Spores",
    "Register Grow Provenance",
    "+ Add Strain",
  ])
    expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
  await u.click(screen.getByRole("link", { name: "Inventory" }));
  expect(
    screen.getByRole("link", { name: "Receive Acquisition" }),
  ).toHaveAttribute("href", "/inventory/receive-acquisition");
  expect(screen.getByRole("link", { name: "Add Strain" })).toHaveAttribute(
    "href",
    "/inventory/strains/new",
  );
  await u.click(screen.getByRole("link", { name: "Receive Acquisition" }));
  expect(await screen.findByLabelText("Acquired material")).toBeInTheDocument();
});
test.each([
  ["acquire", "/inventory/receive-acquisition"],
  ["add-strain", "/inventory/strains/new"],
  ["receive-culture", "/inventory/receive-culture"],
  ["receive-spores", "/inventory/receive-spores"],
  ["register-grow", "/cultivation/register-grow"],
])("legacy %s redirects with context preserved", async (legacy, to) => {
  mock();
  mount(`/culture-library/${legacy}?strain=STR-0001&line=CL-0001`);
  await waitFor(() =>
    expect(screen.getByLabelText("Current route")).toHaveTextContent(
      `${to}?strain=STR-0001&line=CL-0001`,
    ),
  );
});
