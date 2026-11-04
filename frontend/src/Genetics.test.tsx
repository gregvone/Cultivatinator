import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Genetics from "./pages/Genetics";
import { layoutGraph } from "./genetics";
import type { GeneticGraph, GeneticNode } from "./genetics";
const node = (id: string, strain_id: string | null = "s"): GeneticNode => ({
  id,
  name: id,
  strain_id,
  status: "active",
  origin_type: "external",
  source: null,
  photo: null,
  photo_source: "none",
  photos: [],
  fruiting_sources: [],
  can_isolate: true,
});
const fixture = (): GeneticGraph => ({
  strains: [
    { id: "s", name: "Oyster", status: "active", cover: null },
    { id: "t", name: "Lion’s mane", status: "active", cover: null },
  ],
  nodes: [
    node("root"),
    { ...node("child"), status: "archived", origin_type: "spores" },
    node("independent"),
    node("unknown", null),
  ],
  edges: [{ parent_id: "root", line_id: "child", confidence: "possible" }],
});
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(fixture()) }),
      ),
  );
});
afterEach(() => vi.unstubAllGlobals());
test("deterministic layout preserves independent roots, uncertainty and shared branches", () => {
  const d = fixture(),
    a = layoutGraph(d, "s", false, new Set());
  expect(a.positions.get("root")!.y).toBeLessThan(a.positions.get("child")!.y);
  expect(a.positions.get("independent")!.y).toBe(a.positions.get("root")!.y);
  expect(layoutGraph(d, "s", false, new Set()).positions).toEqual(a.positions);
  expect(
    layoutGraph(d, "s", false, new Set(["root"])).nodes.map((n) => n.id),
  ).not.toContain("child");
  d.edges.push({
    parent_id: "independent",
    line_id: "child",
    confidence: "possible",
  });
  expect(
    layoutGraph(d, "s", false, new Set(["root"])).nodes.map((n) => n.id),
  ).toContain("child");
  expect(layoutGraph(d, "s", true, new Set()).headers.map((h) => h.id)).toEqual(
    ["s", "t", "unknown"],
  );
});
test("selection, archived records, collapse, zoom, list and family navigation", async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter>
      <Genetics />
    </MemoryRouter>,
  );
  const child = await screen.findByRole("button", {
    name: /child · child · Spore-derived · archived/,
  });
  await user.click(child);
  const details = screen.getByRole("complementary");
  expect(within(details).getByText("child · archived")).toBeInTheDocument();
  expect(
    within(details).getByText("possible", { exact: false }),
  ).toBeInTheDocument();
  expect(
    within(details).queryByRole("button", { name: "Create Isolate" }),
  ).not.toBeInTheDocument();
  expect(
    within(details).queryByRole("button", { name: "Establish Tissue Clone" }),
  ).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "Collapse descendants" }),
  );
  expect(
    screen.queryByRole("button", { name: /child · child · Spore-derived/ }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Expand All" }));
  await user.click(screen.getByRole("button", { name: "Zoom Out" }));
  expect(
    within(details).getByRole("heading", { name: "child" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Magic Kingdom" }));
  await user.type(screen.getByRole("searchbox"), "unknown");
  await user.click(
    screen.getAllByRole("button", { name: "unknown · unknown · active" })[0],
  );
  await user.click(
    within(details).getByRole("button", { name: "Focus on This Family" }),
  );
  expect(screen.getByRole("combobox", { name: "Strain" })).toHaveValue(
    "unknown",
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith("/api/genetics", expect.any(Object));
});
test("failures are visible and retryable", async () => {
  vi.mocked(fetch).mockRejectedValueOnce(new Error("offline"));
  render(
    <MemoryRouter>
      <Genetics />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  await userEvent.click(screen.getByRole("button", { name: "Retry genetics" }));
  await screen.findByRole("button", { name: /root · root · Acquired/ });
});
test("hundreds of lines use one graph request and stable positions", () => {
  const d = fixture();
  d.nodes = Array.from({ length: 600 }, (_, i) => node(`CL-${i}`));
  d.edges = [];
  const a = layoutGraph(d, "s", true, new Set());
  expect(a.positions.size).toBe(600);
  expect(
    new Set([...a.positions.values()].map((p) => `${p.x},${p.y}`)).size,
  ).toBe(600);
});

test("large kingdom renders readable family summaries instead of hundreds of tiny cards", async () => {
  const d = fixture();
  d.nodes = Array.from({ length: 600 }, (_, i) => node(`CL-${i}`));
  d.edges = [];
  vi.mocked(fetch).mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(d),
  } as Response);
  const { container } = render(
    <MemoryRouter initialEntries={["/genetics?view=kingdom"]}>
      <Genetics />
    </MemoryRouter>,
  );
  await screen.findByRole("region", { name: "Magic Kingdom" });
  await waitFor(() =>
    expect(container.querySelector(".genetic-overview")).toBeInTheDocument(),
  );
  expect(container.querySelectorAll(".genetic-node")).toHaveLength(0);
  expect(
    screen.getAllByRole("button", { name: "Focus on This Family" }),
  ).toHaveLength(3);
  expect(fetch).toHaveBeenCalledTimes(1);
});
