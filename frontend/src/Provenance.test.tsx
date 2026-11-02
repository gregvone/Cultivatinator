import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AcquisitionForm, GrowForm, LineagePanel } from "./pages/Provenance";
import type { LibraryRecord } from "./libraryApi";
const line = {
  id: "CL-0001",
  kind: "lines",
  name: "Original line",
  status: "active",
  strain_id: "STR-0001",
} as LibraryRecord;
const spawn = {
  id: "SJ-0001",
  kind: "spawn",
  line_id: line.id,
  strain_id: line.strain_id,
  strain_name: "Oyster",
  stage: "ready",
} as LibraryRecord;
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}
function mock() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/strains?"))
        return response([{ id: "STR-0001", name: "Oyster" }]);
      if (url.includes("/lines?")) return response([line]);
      if (url.includes("/spawn?"))
        return response([
          spawn,
          {
            ...spawn,
            id: "SB-0001",
            line_id: "CL-0002",
            strain_id: "STR-0002",
            strain_name: "Chestnut",
          },
        ]);
      if (init?.method === "POST" || init?.method === "PUT")
        return response(
          { detail: "Simulated validation rejection; entries retained" },
          422,
        );
      return response({
        origin_type: "clone",
        ancestry_status: "uncertain",
        revision: 3,
        parents: [{ parent_id: line.id, confidence: "possible" }],
        relationships: [
          { label: "Possible genetic parent", record: line },
          {
            label: "Documented fruiting source line · not a parent assertion",
            record: line,
          },
        ],
        warnings: [],
        provenance_mode: "Manual provenance",
      });
    });
}
test("universal acquisition preserves values through review and posts inline strain with ready spawn", async () => {
  const fetch = mock();
  const u = userEvent.setup();
  render(
    <MemoryRouter>
      <AcquisitionForm />
    </MemoryRouter>,
  );
  await screen.findByLabelText("Acquired material");
  await u.selectOptions(screen.getByLabelText("Strain selection"), "new");
  await u.type(screen.getByLabelText("Strain name *"), "New Oyster");
  await u.type(screen.getByLabelText("Supplier / source"), "Supplier A");
  await u.click(screen.getByRole("button", { name: "Review acquisition" }));
  expect(screen.getByText(/genetic ancestry unknown/)).toBeInTheDocument();
  await u.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByLabelText("Supplier / source")).toHaveValue("Supplier A");
  await u.click(screen.getByRole("button", { name: "Review acquisition" }));
  await u.click(screen.getByRole("button", { name: "Confirm acquisition" }));
  await screen.findByRole("alert");
  const call = fetch.mock.calls.find(([url]) =>
    String(url).endsWith("/acquisitions"),
  )!;
  expect(JSON.parse(call[1]?.body as string)).toMatchObject({
    entry_type: "spawn_jar",
    stage: "ready",
    count: 1,
    inline_strain: { name: "New Oyster" },
    line: { supplier: "Supplier A" },
  });
  expect(screen.getByText(/New Oyster/)).toBeInTheDocument();
});
test("spore acquisition only creates spore source and never posts a culture line", async () => {
  const fetch = mock();
  const u = userEvent.setup();
  render(
    <MemoryRouter>
      <AcquisitionForm />
    </MemoryRouter>,
  );
  await screen.findByLabelText("Acquired material");
  await u.selectOptions(
    screen.getByLabelText("Acquired material"),
    "spore_print",
  );
  await u.click(screen.getByRole("button", { name: "Review acquisition" }));
  expect(screen.getByText(/A spore source only/)).toBeInTheDocument();
  await u.click(screen.getByRole("button", { name: "Confirm acquisition" }));
  await screen.findByRole("alert");
  expect(
    fetch.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([url]) => url),
  ).toEqual(["/api/library/spores"]);
});
test("grow form warns about mixed sources and records specific allocations without consumption", async () => {
  const fetch = mock();
  const u = userEvent.setup();
  render(
    <MemoryRouter>
      <GrowForm />
    </MemoryRouter>,
  );
  await screen.findByText(/SJ-0001 · Oyster/);
  await u.click(screen.getByLabelText(/SJ-0001 · Oyster/));
  await u.click(screen.getByLabelText(/SB-0001 · Chestnut/));
  expect(screen.getByText(/Mixed culture lines:/)).toBeInTheDocument();
  expect(screen.getByText(/Mixed named strains:/)).toBeInTheDocument();
  await u.selectOptions(screen.getByLabelText("Source allocation"), "specific");
  await u.click(screen.getByLabelText("SJ-0001 · CL-0001"));
  await u.click(
    screen.getByRole("button", { name: "Register manual provenance" }),
  );
  await screen.findByRole("alert");
  const call = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith("/grows") && init?.method === "POST",
  )!;
  const payload = JSON.parse(call[1]?.body as string);
  expect(payload.source_ids).toEqual(["SJ-0001", "SB-0001"]);
  expect(payload.containers[0].source_ids).toEqual(["SJ-0001"]);
  expect(
    fetch.mock.calls.some(([url]) => String(url).includes("/status")),
  ).toBe(false);
});
test("lineage distinguishes possible parent links and submits revision-protected correction", async () => {
  const fetch = mock();
  const u = userEvent.setup();
  render(
    <MemoryRouter>
      <LineagePanel record={line} onChange={() => {}} />
    </MemoryRouter>,
  );
  expect(await screen.findByText("uncertain")).toBeInTheDocument();
  expect(screen.getByText("Possible genetic parent")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /CL-0001/ })[0]).toHaveAttribute(
    "href",
    "/culture-library/lines/CL-0001",
  );
  await u.click(screen.getByRole("button", { name: "Correct ancestry" }));
  await u.type(
    screen.getByLabelText("Correction reason *"),
    "Verified source label",
  );
  await u.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(
      true,
    ),
  );
  const call = fetch.mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(JSON.parse(call[1]?.body as string)).toEqual({
    expected_revision: 3,
    reason: "Verified source label",
    parents: [],
  });
});
