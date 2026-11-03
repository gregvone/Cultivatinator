import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { NewFruiting, FruitingPanel, FruitingList } from "./pages/Fruiting";
import FruitingEnvironmentSettings from "./components/FruitingEnvironment";
import type { LibraryRecord } from "./libraryApi";
import type { FruitingDetail, Harvest } from "./fruitingApi";
const spawn = {
  id: "SJ-0001",
  kind: "spawn",
  physical_label: "J-01",
  material_type: "spawn_jar",
  stage: "ready",
  lifecycle: "active",
  status: "active",
} as LibraryRecord;
const record = {
  id: "FR-0001",
  kind: "fruiting",
  physical_label: "F-01",
  label_reusable: true,
  label_occupied: true,
  material_type: "tray",
  stage: "colonizing",
  fruiting_stage: "colonizing",
  current_flush: 1,
  lifecycle: "active",
  status: "active",
  strain_name: "Oyster",
  created_at: "2026-01-01",
} as LibraryRecord;
const formula = {
  id: "RCP-1",
  name: "Oyster Substrate",
  recipe_type: "substrate",
  status: "active",
  revision: 1,
  ingredients: [{ name: "Hardwood", quantity: "1000", unit: "g" }],
};
const results = {
  harvest_count: 0,
  wet_grams: null,
  dry_grams: null,
  wet_measured_count: 0,
  dry_measured_count: 0,
  flushes_with_harvests: 0,
  first_harvest_date: null,
  days_to_first_pinning: null,
  days_to_first_harvest: null,
  cycle_days: null,
};
function fixture(stage = "colonizing"): FruitingDetail {
  return {
    record: { ...record, fruiting_stage: stage },
    source: { ...spawn, stage: "used", physical_label: "J-01" },
    legacy: false,
    run: {
      stage,
      current_flush: 1,
      spawning_date: "2026-01-01",
      recipe_snapshot: formula,
      environment_snapshot: null,
      spawn_grams: null,
      substrate_grams: null,
      completed_date: null,
      failed_date: null,
      closing_notes: null,
    },
    harvests: [],
    flushes: [
      { number: 1, pinning_date: null, fruiting_date: null, ...results },
    ],
    environment: null,
    environment_changes: [],
    results: { ...results },
  };
}
function response(value: unknown) {
  return new Response(JSON.stringify(value), { status: 200 });
}
function mock(detail = fixture()) {
  const state = { detail, fresh: spawn };
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = new URL(String(input), "http://test").pathname;
      if (init?.method === "POST") {
        const data =
          init.body instanceof FormData
            ? null
            : JSON.parse(init.body as string);
        if (path.endsWith("/create"))
          return response({
            containers: Array.from({ length: data.count }, (_, index) => ({
              ...record,
              id: `FR-000${index + 1}`,
              physical_label: `F-0${index + 1}`,
            })),
          });
        if (path.endsWith("/stage")) {
          state.detail.run!.stage =
            data.action === "next_flush"
              ? "pinning"
              : data.action === "complete"
                ? "completed"
                : data.action;
          if (data.action === "next_flush")
            state.detail.run!.current_flush += 1;
          state.detail.record.fruiting_stage = state.detail.run!.stage;
          state.detail.record.label_occupied = !["complete", "failed"].includes(
            data.action,
          );
          return response(state.detail);
        }
        if (path.endsWith("/environment"))
          return response({ revision: 1, environment: data.environment });
        if (path.endsWith("/photos"))
          return response({
            id: "photo-1",
            url: "/api/library/photos/photo-1/original",
            thumbnail_url: "/api/library/photos/photo-1/thumbnail",
          });
        return response({ id: "HR-0001", ...data });
      }
      if (path.endsWith("/spawn/SJ-0001")) return response(state.fresh);
      if (path.endsWith("/recipes")) return response([formula]);
      if (path.endsWith("/available"))
        return response({ available: [], next_label: "F-01", reusable: true });
      if (path.endsWith("/environment"))
        return response({ revision: 0, environment: null });
      if (path.endsWith("/photos") || path.endsWith("/history"))
        return response([]);
      if (path.includes("/fruiting/records/")) return response(state.detail);
      if (path === "/api/fruiting/")
        return response([
          state.detail.record,
          {
            ...record,
            id: "FR-0002",
            physical_label: "F-02",
            fruiting_stage: "completed",
            lifecycle: "completed",
            stage: "finished",
          },
        ]);
      return response([]);
    });
  return { state, fetch };
}
function mount(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

test("one Ready spawn creates multiple independently linked F labels without mixing or stock setup", async () => {
  const { fetch } = mock();
  mount(<NewFruiting source={spawn} sourceControl={<p>J-01 source</p>} />);
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Substrate recipe *"),
    formula.id,
  );
  await user.clear(screen.getByLabelText("Number of fruiting containers *"));
  await user.type(
    screen.getByLabelText("Number of fruiting containers *"),
    "3",
  );
  await user.click(
    screen.getByRole("button", { name: "Create Fruiting Containers" }),
  );
  expect(
    await screen.findByRole("heading", {
      name: "Created 3 fruiting containers",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open F-03" })).toHaveAttribute(
    "href",
    "/culture-library/fruiting/FR-0003",
  );
  expect(
    screen.getByRole("button", { name: "Copy Labels" }),
  ).toBeInTheDocument();
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  const payload = JSON.parse(post[1]!.body as string);
  expect(payload).toMatchObject({
    spawn_id: "SJ-0001",
    count: 3,
    recipe_id: "RCP-1",
    material_type: "tray",
  });
  expect(payload.source_ids).toBeUndefined();
  expect(payload.spawn_grams).toBeNull();
  expect(
    screen.queryByLabelText(/inventory|equipment stock/i),
  ).not.toBeInTheDocument();
});

test("a selected spawn becoming Used is rejected before creating fruiting records", async () => {
  const { state, fetch } = mock();
  state.fresh = { ...spawn, stage: "used", lifecycle: "used" };
  mount(<NewFruiting source={spawn} sourceControl={<p>Source</p>} />);
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Substrate recipe *"),
    formula.id,
  );
  await user.click(
    screen.getByRole("button", { name: "Create Fruiting Containers" }),
  );
  expect(await screen.findByText(/no longer Ready/)).toBeInTheDocument();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
    false,
  );
});

test("grow details show Colonizing and only explicit dated stage actions", async () => {
  const { fetch } = mock();
  mount(<FruitingPanel record={record} onSaved={vi.fn()} />);
  expect(
    await screen.findByText("Current Status: Colonizing"),
  ).toBeInTheDocument();
  expect(screen.getByText("Current flush: 1")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Record Harvest" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/Lifecycle action/)).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Mark Pinning" }));
  await user.clear(screen.getByLabelText("Stage date *"));
  await user.type(screen.getByLabelText("Stage date *"), "2026-01-03");
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  expect(
    await screen.findByText("Current Status: Pinning"),
  ).toBeInTheDocument();
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({
    action: "pinning",
    action_date: "2026-01-03",
  });
  expect(
    screen.getByRole("button", { name: "Mark Fruiting" }),
  ).toBeInTheDocument();
});

test("Record Harvest allows unknown weights and optional subjective potency, with no automatic completion", async () => {
  const { fetch } = mock(fixture("fruiting"));
  mount(
    <FruitingPanel
      record={{ ...record, fruiting_stage: "fruiting" }}
      onSaved={vi.fn()}
    />,
  );
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Record Harvest" }),
  );
  expect(screen.getByText(/not a laboratory assay/)).toBeInTheDocument();
  await user.selectOptions(
    screen.getByLabelText("Subjective medicinal potency (optional)"),
    "4",
  );
  await user.type(screen.getByLabelText("Potency notes"), "Subjective trial");
  await user.click(screen.getByRole("button", { name: "Save Harvest" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith("/harvests") && init?.method === "POST",
      ),
    ).toBe(true),
  );
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({
    wet_grams: null,
    dry_grams: null,
    potency: 4,
    potency_notes: "Subjective trial",
  });
  expect(String(post[0])).not.toContain("stage");
});

const harvest = {
  id: "HR-0001",
  fruiting_id: "FR-0001",
  flush_number: 1,
  harvest_date: "2026-01-07",
  wet_grams: "100.000",
  dry_grams: null,
  potency: null,
  potency_notes: null,
  notes: null,
  revision: 1,
} as Harvest;
test("dry weights can be entered later and exact harvest photos keep their own endpoint", async () => {
  const d = fixture("harvest");
  d.harvests = [harvest, { ...harvest, id: "HR-0002" }];
  const { fetch } = mock(d);
  mount(
    <FruitingPanel
      record={{ ...record, fruiting_stage: "harvest" }}
      onSaved={vi.fn()}
    />,
  );
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Edit Harvest HR-0001" }),
  );
  await user.type(screen.getByLabelText("Dry weight (g, optional)"), "10");
  await user.click(
    screen.getByRole("button", { name: "Save Harvest Changes" }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([input, init]) =>
          String(input).includes("/harvests/HR-0001/edit") &&
          init?.method === "POST",
      ),
    ).toBe(true),
  );
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({
    dry_grams: "10",
    expected_revision: 1,
  });
  const first = screen
    .getByRole("heading", { name: /Harvest HR-0001/ })
    .closest("section")!;
  await user.upload(within(first).getByLabelText("Attach photographs"), [
    new File(["a"], "one.png", { type: "image/png" }),
    new File(["b"], "two.png", { type: "image/png" }),
  ]);
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter(
        ([input, init]) =>
          String(input).endsWith("/harvests/HR-0001/photos") &&
          init?.method === "POST",
      ),
    ).toHaveLength(2),
  );
  expect(
    fetch.mock.calls.some(
      ([input, init]) =>
        String(input).endsWith("/harvests/HR-0002/photos") &&
        init?.method === "POST",
    ),
  ).toBe(false);
});

test("Next Flush advances to Pinning and Finish Grow stays an explicit separate action", async () => {
  mock(fixture("harvest"));
  mount(
    <FruitingPanel
      record={{ ...record, fruiting_stage: "harvest" }}
      onSaved={vi.fn()}
    />,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Next Flush" }));
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  expect(await screen.findByText("Current flush: 2")).toBeInTheDocument();
  expect(screen.getByText("Current Status: Pinning")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Finish Grow" }));
  expect(screen.getByText(/no more flushes/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  expect(
    await screen.findByText("Current Status: Completed"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Finish Grow" }),
  ).not.toBeInTheDocument();
});

test("optional single-tent settings begin empty and save without any defaults invented", async () => {
  const { fetch } = mock();
  mount(<FruitingEnvironmentSettings />);
  const user = userEvent.setup();
  await user.click(
    await screen.findByText("Configure fruiting tent (optional)"),
  );
  expect(screen.getByLabelText("Target temperature")).toHaveValue(null);
  await user.type(screen.getByLabelText("Tent name"), "One tent");
  await user.click(
    screen.getByRole("button", { name: "Save Fruiting Environment" }),
  );
  expect(await screen.findByText(/saved for future grows/)).toBeInTheDocument();
  const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({
    expected_revision: 0,
    environment: { tent_name: "One tent", temperature: null, humidity: null },
  });
});

test("legacy records show unknown earlier data, and completed grows are hidden from active lists", async () => {
  const d = fixture();
  d.run = null;
  d.source = null;
  d.legacy = true;
  d.flushes = [];
  mock(d);
  const view = mount(
    <FruitingPanel
      record={{ ...record, fruiting_stage: null, stage: "ready" }}
      onSaved={vi.fn()}
    />,
  );
  expect(
    await screen.findByText("Current Status: Stage not recorded"),
  ).toBeInTheDocument();
  expect(screen.getByText("Spawning date: Not recorded")).toBeInTheDocument();
  expect(screen.getByText("Current flush: Not recorded")).toBeInTheDocument();
  view.unmount();
  mount(<FruitingList />);
  expect(await screen.findByRole("link", { name: /F-01/ })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /F-02/ })).not.toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByLabelText("Show fruiting records"),
    "completed",
  );
  expect(screen.getByRole("link", { name: /F-02/ })).toBeInTheDocument();
});
