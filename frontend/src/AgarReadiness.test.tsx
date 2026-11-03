import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import type { LibraryRecord } from "./libraryApi";
import { cultivationStatus } from "./containerApi";
import { eligibleSource, quickCreate, sourceLabel } from "./quickCreate";

const initial = {
  id: "AG-0012",
  kind: "physical",
  material_type: "agar_plate",
  physical_label: "P-05",
  label_reusable: true,
  label_occupied: true,
  growth_stage: "colonizing",
  lifecycle: "active",
  status: "active",
  strain_name: "Oyster",
  line_id: "CL-1",
  strain_id: null,
  quantity: null,
  name: null,
  created_at: "2026-11-01",
  ready_date: null,
} as LibraryRecord;
const lc = {
  ...initial,
  id: "LC-0001",
  physical_label: "L-01",
  material_type: "lc_jar",
  growth_stage: null,
} as LibraryRecord;
const spores = {
  ...initial,
  id: "SP-0001",
  kind: "spores",
  material_type: "spore_print",
  growth_stage: null,
} as LibraryRecord;
const recipe = {
  id: "RCP-1",
  name: "Standard Agar",
  status: "active",
  recipe_type: "agar",
  ingredients: [],
  batch_yield: 1,
};
function setup(overrides: Partial<LibraryRecord> = {}) {
  const state = {
    plate: { ...initial, ...overrides },
    fresh: null as LibraryRecord | null,
    loseResponse: false,
  };
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = new URL(String(input), "http://test").pathname;
      let data: unknown = [];
      if (init?.method === "POST" && path.endsWith("/state")) {
        const body = JSON.parse(init.body as string);
        state.plate = {
          ...state.plate,
          growth_stage: body.action,
          ready_date: body.action_date,
        };
        data = state.plate;
      } else if (init?.method === "POST" && path.endsWith("/create")) {
        state.plate = {
          ...state.plate,
          growth_stage: "used",
          lifecycle: "used",
          label_occupied: false,
        };
        if (state.loseResponse) {
          state.loseResponse = false;
          throw new Error("Response lost after transfer");
        }
        data = {
          materials: [
            {
              ...initial,
              id: "AG-0013",
              physical_id: "AG-0013",
              physical_label: "P-06",
            },
          ],
        };
      } else if (path === "/api/library/physical/AG-0012")
        data = state.fresh || state.plate;
      else if (path === "/api/library/physical") data = [state.plate, lc];
      else if (path === "/api/library/spores") data = [spores];
      else if (path === "/api/preparation/growing")
        data = [{ ...state.plate, cultivation: null }];
      else if (path.startsWith("/api/preparation/records/"))
        data = { preparation: null, destinations: [] };
      else if (path.startsWith("/api/provenance/"))
        data = {
          parents: [],
          relationships: [],
          warnings: [],
          ancestry_status: "unknown",
          origin_type: "external",
        };
      else if (path === "/api/preparation/recipes") data = [recipe];
      else if (path === "/api/preparation/lc-default") data = { recipe: null };
      else if (path === "/api/containers/available")
        data = { available: [], next_label: "P-06", reusable: true };
      return new Response(JSON.stringify(data), { status: 200 });
    });
  return { state, fetch };
}
function mount(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

test("new agar details show Germinating and one explicit readiness control, then agree with Laboratory", async () => {
  const { state } = setup();
  const view = mount("/culture-library/physical/AG-0012");
  expect(
    await screen.findByText("Current Status: Germinating"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Mark Failed" }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText(/Lifecycle action/i)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Complete/ }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Create From This")).not.toBeInTheDocument();
  expect(screen.getByText("Active", { selector: "dd" })).toBeInTheDocument(); // explicitly Record visibility
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Mark Ready" }));
  await user.click(screen.getByRole("button", { name: "Save Status" }));
  expect(await screen.findByText("Current Status: Ready")).toBeInTheDocument();
  expect(state.plate.growth_stage).toBe("ready");
  expect(
    screen.queryByRole("button", { name: "Mark Ready" }),
  ).not.toBeInTheDocument();
  expect(await screen.findByText("Create From This")).toBeInTheDocument();
  view.unmount();
  mount("/laboratory");
  expect(await screen.findByText("Current Status: Ready")).toBeInTheDocument();
});

test("legacy Active agar shows unrecorded readiness and can explicitly become Ready", async () => {
  setup({ growth_stage: null, ready_date: null });
  mount("/culture-library/physical/AG-0012");
  expect(
    await screen.findByText("Current Status: Readiness not recorded"),
  ).toBeInTheDocument();
  expect(screen.queryByText(/Ready date:/)).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Mark Ready" }));
  await user.click(screen.getByRole("button", { name: "Save Status" }));
  expect(await screen.findByText("Current Status: Ready")).toBeInTheDocument();
});

test.each(["agar-plate", "lc-container", "spawn"])(
  "only Ready agar is offered by %s, while LC/spore eligibility stays independent",
  async (operation) => {
    const { state } = setup();
    const view = mount(
      `/quick-create/${operation}?source_kind=physical&source_id=AG-0012`,
    );
    const selector = await screen.findByRole("combobox", {
      name: "Source material",
    });
    await screen.findByText(/linked source is unavailable/);
    expect(
      screen.getByRole("link", {
        name: "Open source record to review readiness",
      }),
    ).toHaveAttribute("href", "/culture-library/physical/AG-0012");
    expect(
      within(selector).queryByRole("option", { name: /AG-0012/ }),
    ).not.toBeInTheDocument();
    expect(
      within(selector).getByRole("option", { name: /LC-0001/ }),
    ).toBeInTheDocument();
    if (operation === "agar-plate")
      expect(
        within(selector).getByRole("option", { name: /SP-0001/ }),
      ).toBeInTheDocument();
    view.unmount();
    state.plate = { ...state.plate, growth_stage: "ready" };
    mount(`/quick-create/${operation}?source_kind=physical&source_id=AG-0012`);
    const ready = await screen.findByRole("option", {
      name: /P-05.*AG-0012.*Ready/,
    });
    expect(ready).toBeInTheDocument();
    expect(
      await screen.findByText(/Current Status: Ready/),
    ).toBeInTheDocument();
  },
);

test.each(["failed", "used", "colonizing"])(
  "an already selected agar source becoming %s is rejected before a creation POST",
  async (phase) => {
    const { state, fetch } = setup({ growth_stage: "ready" });
    mount("/quick-create/agar-plate?source_kind=physical&source_id=AG-0012");
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Agar recipe *"),
      "RCP-1",
    );
    await screen.findByText(/Current Status: Ready/);
    state.fresh = {
      ...state.plate,
      growth_stage: phase,
      lifecycle: phase === "colonizing" ? "active" : phase,
    };
    await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
    expect(
      await screen.findByText(/agar source is no longer eligible/),
    ).toBeInTheDocument();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      false,
    );
  },
);

test("successful Ready agar creation displays Germinating destinations and Used source consistently", async () => {
  const { state } = setup({ growth_stage: "ready" });
  const view = mount(
    "/quick-create/agar-plate?source_kind=physical&source_id=AG-0012",
  );
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Agar recipe *"),
    "RCP-1",
  );
  await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByText("Current Status: Germinating"),
  ).toBeInTheDocument();
  expect(state.plate.lifecycle).toBe("used");
  view.unmount();
  mount("/culture-library/physical/AG-0012");
  expect(await screen.findByText("Current Status: Used")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Mark Ready" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/Released/)).toBeInTheDocument();
});

test("agar Germinating mapping does not rename spawn colonization or require LC/spore agar readiness", () => {
  const agar = quickCreate.find((op) => op.id === "agar-plate")!;
  expect(cultivationStatus(initial)).toBe("Germinating");
  for (const source of [lc, spores])
    expect(eligibleSource(agar, source)).toBe(true);
  const spawn = {
    ...initial,
    kind: "spawn",
    material_type: "spawn_jar",
    stage: "colonizing",
  } as LibraryRecord;
  expect(cultivationStatus(spawn)).toBe("Colonizing");
  expect(sourceLabel({ ...initial, growth_stage: "ready" })).toContain("Ready");
  for (const growth_stage of [null, "colonizing", "failed", "used"])
    expect(eligibleSource(agar, { ...initial, growth_stage })).toBe(false);
});

test("a lost response can replay the same request after the source becomes Used", async () => {
  const { state, fetch } = setup({ growth_stage: "ready" });
  state.loseResponse = true;
  mount("/quick-create/agar-plate?source_kind=physical&source_id=AG-0012");
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Agar recipe *"),
    "RCP-1",
  );
  await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByText("Response lost after transfer"),
  ).toBeInTheDocument();
  expect(state.plate.lifecycle).toBe("used");
  await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByRole("heading", { name: "Created 1 record" }),
  ).toBeInTheDocument();
  const posts = fetch.mock.calls.filter(
    ([input, init]) =>
      String(input).endsWith("/create") && init?.method === "POST",
  );
  expect(posts).toHaveLength(2);
  expect(JSON.parse(posts[0][1]!.body as string).request_key).toBe(
    JSON.parse(posts[1][1]!.body as string).request_key,
  );
  expect(
    fetch.mock.calls.filter(([input]) =>
      String(input).endsWith("/physical/AG-0012"),
    ),
  ).toHaveLength(1);
});

test("editing a command after a lost response rechecks readiness rather than reusing the consumed source", async () => {
  const { state, fetch } = setup({ growth_stage: "ready" });
  state.loseResponse = true;
  mount("/quick-create/agar-plate?source_kind=physical&source_id=AG-0012");
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Agar recipe *"),
    "RCP-1",
  );
  await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
  await screen.findByText("Response lost after transfer");
  await user.clear(screen.getByLabelText("Number of containers *"));
  await user.type(screen.getByLabelText("Number of containers *"), "2");
  await user.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByText(/agar source is no longer eligible/),
  ).toBeInTheDocument();
  expect(
    fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(1);
});
