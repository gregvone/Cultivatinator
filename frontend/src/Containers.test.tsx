import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ContainerTracking from "./components/ContainerTracking";
import DirectCreate from "./pages/DirectCreate";
import Growing from "./pages/Growing";
import { quickCreate, eligibleSource, sourceLabel } from "./quickCreate";
import { localToday, title } from "./libraryApi";
import type { LibraryRecord } from "./libraryApi";
const plate = {
  id: "AG-0012",
  kind: "physical",
  material_type: "agar_plate",
  physical_label: "P-05",
  label_reusable: true,
  label_occupied: true,
  growth_stage: "colonizing",
  lifecycle: "active",
  status: "active",
  strain_name: "Lion’s Mane",
  created_at: "2026-11-01",
  line_id: "CL-1",
} as LibraryRecord;
function response(data: unknown) {
  return new Response(JSON.stringify(data), { status: 200 });
}
function mount(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}
const formula = {
  id: "RCP-1",
  name: "Agar formula",
  recipe_type: "agar",
  status: "active",
};
function mock() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      if (init?.method === "POST")
        return response({
          materials: [
            { id: "AG-0024", physical_id: "AG-0024", physical_label: "P-05" },
            { id: "AG-0025", physical_id: "AG-0025", physical_label: "P-06" },
          ],
        });
      if (String(input).includes("/containers/available"))
        return response({
          available: ["P-02", "P-05"],
          next_label: "P-06",
          reusable: true,
        });
      if (String(input).endsWith("/recipes")) return response([formula]);
      return response([]);
    });
}
test("physical labels lead titles and selectors while permanent IDs remain distinct", () => {
  expect(title(plate)).toBe("P-05 — Lion’s Mane");
  expect(sourceLabel(plate)).toMatch(/^P-05/);
  expect(sourceLabel(plate)).toContain("AG-0012");
  const op = quickCreate.find((o) => o.id === "spawn")!;
  expect(eligibleSource(op, plate)).toBe(false);
  expect(eligibleSource(op, { ...plate, growth_stage: "ready" })).toBe(true);
  expect(
    eligibleSource(op, { ...plate, growth_stage: "used", lifecycle: "used" }),
  ).toBe(false);
});
test("Mark Ready is explicit and offers today's local date with an override", async () => {
  const fetch = mock();
  const saved = vi.fn();
  mount(<ContainerTracking record={plate} onSaved={saved} />);
  const u = userEvent.setup();
  await u.click(screen.getByRole("button", { name: "Mark Ready" }));
  expect(screen.getByLabelText("Lifecycle date")).toHaveValue(localToday());
  await u.clear(screen.getByLabelText("Lifecycle date"));
  await u.type(screen.getByLabelText("Lifecycle date"), "2026-10-31");
  await u.click(screen.getByRole("button", { name: "Save Status" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(call[0]).toBe("/api/containers/records/physical/AG-0012/state");
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({
    action: "ready",
    action_date: "2026-10-31",
    reason: null,
  });
  expect(saved).toHaveBeenCalledOnce();
});
test("legacy active records offer Assign Label without equipment stock registration", async () => {
  const fetch = mock();
  mount(
    <ContainerTracking
      record={{
        ...plate,
        physical_label: null,
        label_occupied: false,
        growth_stage: null,
      }}
      onSaved={vi.fn()}
    />,
  );
  const u = userEvent.setup();
  await u.click(screen.getByRole("button", { name: "Assign Label" }));
  await u.click(screen.getByRole("button", { name: "Save Label" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(call[0]).toBe("/api/containers/records/physical/AG-0012/label");
  expect(screen.queryByLabelText(/stock|capacity/i)).not.toBeInTheDocument();
});
test("depleted LC retains its physical label and provides explicit retirement", () => {
  mock();
  mount(
    <ContainerTracking
      record={{
        ...plate,
        id: "LC-1",
        physical_label: "L-01",
        material_type: "lc_jar",
        growth_stage: null,
        lifecycle: "depleted",
      }}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByText("Occupied", { exact: false })).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Complete / Retire Container" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Mark Ready" }),
  ).not.toBeInTheDocument();
});
test("Used agar exposes history but no readiness, label or source actions", () => {
  mock();
  mount(
    <ContainerTracking
      record={{
        ...plate,
        growth_stage: "used",
        lifecycle: "used",
        label_occupied: false,
      }}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByText("Permanent record: AG-0012")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Mark Ready" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Assign Label" }),
  ).not.toBeInTheDocument();
});
test("manual bulk label overrides submit separately from permanent identifiers", async () => {
  const fetch = mock();
  const source = {
    ...plate,
    id: "LC-1",
    material_type: "lc_jar",
    remaining_quantity: null,
  } as LibraryRecord;
  mount(
    <DirectCreate
      operation="agar-plate"
      source={source}
      sourceControl={<p>LC source</p>}
    />,
  );
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText("Agar recipe *"), "RCP-1");
  await u.clear(screen.getByLabelText("Number of containers *"));
  await u.type(screen.getByLabelText("Number of containers *"), "2");
  await u.click(screen.getByText(/Physical labels · automatic/));
  await u.selectOptions(
    await screen.findByLabelText("Container 2 physical label"),
    "P-05",
  );
  await u.click(screen.getByRole("button", { name: "Create Agar plate" }));
  expect(
    await screen.findByText("P-05, P-06", { selector: "p" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open P-05" })).toHaveAttribute(
    "href",
    "/culture-library/physical/AG-0024",
  );
  expect(screen.getByText("Permanent record: AG-0024")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Copy Labels" }),
  ).toBeInTheDocument();
  const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(call[1]!.body as string).label_choices).toEqual([
    {},
    { label: "P-05" },
  ]);
});
test("growing lists show physical labels first and Used records only through filtering", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    response([
      {
        ...plate,
        cultivation: {
          source: {
            kind: "physical",
            id: "LC-0020",
            physical_label: "L-01",
            date: "2026-11-02",
          },
          snapshot: {},
        },
      },
      {
        ...plate,
        id: "AG-0024",
        physical_label: "P-01",
        growth_stage: "used",
        lifecycle: "used",
        cultivation: null,
      },
    ]),
  );
  mount(<Growing workspace="laboratory" />);
  expect(
    await screen.findByRole("link", { name: "P-05 · Agar plate" }),
  ).toHaveAttribute("href", "/culture-library/physical/AG-0012");
  expect(screen.getByText("Permanent record: AG-0012")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "L-01" })).toHaveAttribute(
    "href",
    "/culture-library/physical/LC-0020",
  );
  expect(
    screen.queryByRole("link", { name: "P-01 · Agar plate" }),
  ).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Show records"), "used");
  expect(
    screen.getByRole("link", { name: "P-01 · Agar plate" }),
  ).toHaveAttribute("href", "/culture-library/physical/AG-0024");
});
