import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import StrainIdentity from "./components/StrainIdentity";
import { CultureLibrary, RecordDetail } from "./pages/CultureLibrary";
import { Route, Routes } from "react-router-dom";
import type { LibraryRecord } from "./libraryApi";
const oyster = { id: "STR-0001", name: "Oyster" };
const chestnut = { id: "STR-0002", name: "Chestnut" };
const record = {
  id: "FR-0001",
  kind: "fruiting",
  name: null,
  status: "active",
  created_at: "2026-01-01",
  strain_id: null,
  strain_name: null,
  quantity: null,
} as LibraryRecord;

test.each([
  ["known", [oyster], "Oyster"],
  ["mixed", [oyster, chestnut], "Mixed Strains: Oyster, Chestnut"],
  ["partial", [oyster], "Partial identification: Oyster; Unknown sources"],
  [
    "partial",
    [oyster, chestnut],
    "Mixed Strains · Partial identification: Oyster, Chestnut; Unknown sources",
  ],
  ["unknown", [], "Unknown"],
] as const)("FR strain display: %s, %j", (state, strains, label) => {
  const { container } = render(
    <MemoryRouter>
      <StrainIdentity
        record={{
          ...record,
          strain_identification: state,
          contributing_strains: [...strains],
        }}
      />
    </MemoryRouter>,
  );
  expect(container).toHaveTextContent(label);
  for (const strain of strains)
    expect(screen.getByRole("link", { name: strain.name })).toHaveAttribute(
      "href",
      `/culture-library/strains/${strain.id}`,
    );
});

test("FR list and properties use the same derived partial identity", async () => {
  const fruit = {
    ...record,
    strain_identification: "partial" as const,
    contributing_strains: [oyster],
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    let data: unknown = [];
    if (url.includes("/provenance/"))
      data = {
        origin_type: "prepared",
        ancestry_status: "unknown",
        revision: 0,
        parents: [],
        relationships: [],
        warnings: ["Some strain identities are unknown"],
        provenance_mode: "Manual provenance",
      };
    else if (url.endsWith("/fruiting/FR-0001")) data = fruit;
    else if (url.includes("/fruiting?")) data = [fruit];
    return new Response(JSON.stringify(data), { status: 200 });
  });
  render(
    <MemoryRouter initialEntries={["/culture-library"]}>
      <Routes>
        <Route path="/culture-library" element={<CultureLibrary />} />
        <Route path="/culture-library/:kind/:code" element={<RecordDetail />} />
      </Routes>
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Fruiting Containers" }));
  expect(await screen.findByText(/Partial identification:/)).toHaveTextContent(
    "Partial identification: Oyster; Unknown sources",
  );
  await user.click(screen.getByRole("link", { name: /FR-0001 · active/ }));
  const properties = await screen.findByRole("heading", {
    name: "Record information",
  });
  const panel = properties.closest("section")!;
  expect(panel).toHaveTextContent(
    "Partial identification: Oyster; Unknown sources",
  );
  expect(within(panel).getByRole("link", { name: "Oyster" })).toHaveAttribute(
    "href",
    "/culture-library/strains/STR-0001",
  );
  expect(
    await screen.findByText("Some strain identities are unknown"),
  ).toBeInTheDocument();
});
