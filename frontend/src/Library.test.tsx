import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { localToday } from "./libraryApi";
const strain = {
  id: "STR-0001",
  kind: "strains",
  name: "Test strain",
  status: "active",
  created_at: "2026-01-02T10:00:00Z",
  line_count: 1,
  spore_count: 0,
  physical_count: 3,
  cover: null,
};
const line = {
  ...strain,
  kind: "lines",
  id: "CL-0001",
  name: "Supplier batch",
  strain_id: strain.id,
  strain_name: strain.name,
  origin: "purchased",
  supplier: "Original supplier",
  acquisition_date: "2025-03-04",
};
function mount(path = "/culture-library") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}
function mockLibrary(empty = false) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method || "GET";
      if (url.includes("/api/preparation/")) return response([]);
      if (url.includes("/api/provenance/"))
        return response({
          origin_type: "external",
          ancestry_status: "unknown",
          revision: 1,
          parents: [],
          relationships: [],
          warnings: [],
        });
      if (url.endsWith("/activity") || url.endsWith("/photos"))
        return response([]);
      if (url.includes("/library/strains?"))
        return response(empty ? [] : [strain]);
      if (url.includes("/library/lines?")) return response(empty ? [] : [line]);
      if (
        url.includes("/library/spores?") ||
        url.includes("/library/physical?")
      )
        return response([]);
      if (method === "POST" && url.endsWith("/strains"))
        return response(
          { ...strain, ...JSON.parse(init?.body as string) },
          201,
        );
      if (method === "POST" && url.endsWith("/receive-culture"))
        return response({ line, physical: [] }, 201);
      if (url.endsWith("/lines/CL-0001")) return response(line);
      if (url.endsWith("/spores") || url.endsWith("/spores/SP-0001"))
        return response({ ...strain, kind: "spores", id: "SP-0001" }, 201);
      return response(strain);
    });
}
test("empty catalog links to Inventory for strain management", async () => {
  const fetch = mockLibrary(true);
  mount();
  const u = userEvent.setup();
  expect(
    await screen.findByText("Your strain catalog starts here."),
  ).toBeInTheDocument();
  await u.click(screen.getByRole("link", { name: "Open Inventory" }));
  await u.click(screen.getByRole("link", { name: "Add Strain" }));
  await u.type(screen.getByLabelText("Strain name *"), "New strain");
  await u.click(screen.getByRole("button", { name: "Create strain" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/library/strains",
      expect.objectContaining({
        method: "POST",
        body: '{"name":"New strain"}',
      }),
    ),
  );
});
test("cards show actual counts, open related lines, and filters query the API", async () => {
  const fetch = mockLibrary();
  mount();
  const u = userEvent.setup();
  const name = await screen.findByRole("heading", { name: "Test strain" });
  expect(screen.getByText("Containers")).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
  await u.click(name);
  expect(
    await screen.findByRole("heading", { name: "Record information" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Supplier batch/ })).toHaveAttribute(
    "href",
    "/culture-library/lines/CL-0001",
  );
  await u.click(screen.getByRole("link", { name: "← Culture Library" }));
  await screen.findByRole("searchbox");
  await u.type(screen.getByRole("searchbox"), "oyster");
  await u.selectOptions(screen.getByLabelText("Status"), "archived");
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("q=oyster&status=archived"),
      expect.anything(),
    ),
  );
});
test("guided registration preserves inline strain and acquisition values through review", async () => {
  const fetch = mockLibrary();
  mount("/culture-library/receive-culture");
  const u = userEvent.setup();
  await screen.findByLabelText("Strain selection");
  await u.selectOptions(screen.getByLabelText("Strain selection"), "new");
  await u.type(screen.getByLabelText("Strain name *"), "Inline strain");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  expect(
    screen.getByLabelText("Acquisition date (leave blank if unknown)"),
  ).toHaveValue(localToday());
  await u.type(screen.getByLabelText("Supplier / source"), "Supplier A");
  await u.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByLabelText("Strain name *")).toHaveValue("Inline strain");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByLabelText("Supplier / source")).toHaveValue("Supplier A");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  await u.click(screen.getByLabelText("Register physical containers now"));
  await u.clear(screen.getByLabelText("Number of containers (1–100) *"));
  await u.type(screen.getByLabelText("Number of containers (1–100) *"), "3");
  await u.type(
    screen.getByLabelText("Starting Quantity per container (optional)"),
    "10",
  );
  await u.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByText("3 × Liquid culture syringe")).toBeInTheDocument();
  await u.click(screen.getByRole("button", { name: "Confirm registration" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/library/receive-culture",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const call = fetch.mock.calls.find(([p]) =>
    String(p).endsWith("/receive-culture"),
  )!;
  const payload = JSON.parse(call[1]!.body as string);
  expect(payload.inline_strain.name).toBe("Inline strain");
  expect(payload.line.supplier).toBe("Supplier A");
  expect(payload.material.count).toBe(3);
});
test("unknown-strain spore registration only posts to spores", async () => {
  const fetch = mockLibrary();
  mount("/culture-library/receive-spores");
  const u = userEvent.setup();
  await screen.findByLabelText("Strain selection");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  await u.type(screen.getByLabelText("Registered Quantity (optional)"), "2");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  await u.click(screen.getByRole("button", { name: "Confirm registration" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/library/spores",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(
    fetch.mock.calls.some(([p]) => String(p).endsWith("/receive-culture")),
  ).toBe(false);
  const call = fetch.mock.calls.find(([p]) => String(p).endsWith("/spores"))!;
  expect(JSON.parse(call[1]!.body as string).strain_id).toBeNull();
  expect(JSON.parse(call[1]!.body as string)).not.toHaveProperty("origin");
});
test("archive requires confirmation and ordinary edits do not reassign relationships", async () => {
  const fetch = mockLibrary();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  mount("/culture-library/strains/STR-0001");
  const u = userEvent.setup();
  await screen.findByRole("button", { name: "Archive record" });
  await u.click(screen.getByRole("button", { name: "Archive record" }));
  expect(fetch.mock.calls.some(([p]) => String(p).endsWith("/status"))).toBe(
    false,
  );
  confirm.mockReturnValue(true);
  await u.click(screen.getByRole("button", { name: "Archive record" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/library/strains/STR-0001/status",
      expect.objectContaining({ body: '{"status":"archived"}' }),
    ),
  );
  await u.click(screen.getByRole("button", { name: "Edit information" }));
  await u.type(screen.getByLabelText("Notes"), "Reference notes");
  await u.click(screen.getByRole("button", { name: "Save changes" }));
  const call = fetch.mock.calls.find(([, init]) => init?.method === "PATCH")!;
  const payload = JSON.parse(call[1]!.body as string);
  expect(payload.notes).toBe("Reference notes");
  expect(payload).not.toHaveProperty("strain_id");
});
test("gallery uploads multiple files and reports rejected image content", async () => {
  const fetch = mockLibrary();
  mount("/culture-library/strains/STR-0001");
  const u = userEvent.setup();
  const input = await screen.findByLabelText("Attach photographs");
  await u.upload(input, [
    new File(["one"], "one.png", { type: "image/png" }),
    new File(["two"], "two.webp", { type: "image/webp" }),
  ]);
  await screen.findByText("2 photograph(s) attached");
  expect(
    fetch.mock.calls.filter(([, init]) => init?.body instanceof FormData),
  ).toHaveLength(2);
  fetch.mockImplementationOnce(async () =>
    response({ detail: "Upload a valid image" }, 422),
  );
  await u.upload(input, new File(["bad"], "bad.png", { type: "image/png" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Upload a valid image",
  );
});

test("adding containers reviews the selected line's actual acquisition and preserves its identity", async () => {
  const fetch = mockLibrary();
  mount("/culture-library/receive-culture?strain=STR-0001&line=CL-0001");
  const u = userEvent.setup();
  await screen.findByLabelText("Strain selection");
  await u.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByLabelText("Existing culture line *")).toHaveValue(
    "CL-0001",
  );
  await u.click(screen.getByRole("button", { name: "Continue" }));
  await u.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByText(/Original supplier.*2025-03-04/)).toBeInTheDocument();
  await u.click(screen.getByRole("button", { name: "Confirm registration" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/library/receive-culture",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const call = fetch.mock.calls.find(([p]) =>
    String(p).endsWith("/receive-culture"),
  )!;
  const payload = JSON.parse(call[1]!.body as string);
  expect(payload.existing_line_id).toBe("CL-0001");
  expect(payload).not.toHaveProperty("line");
});
