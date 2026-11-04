import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Environment, { ReadingTable } from "./pages/Environment";
import { localDateTime, observationTime } from "./environmentApi";
import type { Reading } from "./environmentApi";
import { navigation } from "./navigation";
const tent = {
  id: "ET-1",
  name: "Boom Room 2",
  description: null,
  status: "active",
  revision: 1,
  profile_id: null,
};
const profile = {
  id: "EP-1",
  name: "User draft",
  species: null,
  notes: null,
  status: "active",
  revision: 1,
  targets: { humidity_min: 80 },
};
const reading: Reading = {
  id: 1,
  tent_id: tent.id,
  observed_at: "2025-01-02T12:00:00Z",
  created_at: "2025-01-02T13:00:00Z",
  temperature_f: 70,
  humidity: 50,
  co2: null,
  humidifier: 3,
  fan: null,
  notes: "Dry walls",
  source: "manual",
  snapshot: profile,
  evaluations: { humidity: "low" },
  replaces_id: null,
  correction_reason: null,
  superseded_by: null,
  fruiting_ids: ["FR-1"],
};
let hasTent = false;
function mockFetch() {
  return vi.fn().mockImplementation(async (url: string, o?: RequestInit) => {
    const p = url.replace("/api/environment/", "");
    let data: unknown = [];
    if (o?.method === "POST" && p === "tents") {
      hasTent = true;
      data = tent;
    } else if (p === "tents") data = hasTent ? [tent] : [];
    else if (p.includes("/overview"))
      data = {
        tent,
        profile: null,
        latest: {
          temperature_f: { value: 70, observed_at: reading.observed_at },
          humidity: { value: 50, observed_at: reading.observed_at },
          co2: null,
        },
        warnings: [
          {
            metric: "humidity",
            state: "low",
            value: 50,
            unit: "% RH",
            observed_at: reading.observed_at,
            reading_id: 1,
          },
        ],
        occupancy_count: 0,
      };
    else if (p.includes("/history"))
      data = { items: [], assignments: [], total: 0, page: 1, page_size: 50 };
    else if (p.includes("/readings"))
      data = { items: [reading], total: 1, page: 1, page_size: 100 };
    else if (p.startsWith("occupancy?"))
      data = { items: [], total: 0, page: 1, page_size: 50 };
    else if (p.startsWith("containers?"))
      data = [{ id: "FR-1", title: "F1 · Oyster" }];
    return { ok: true, status: 200, json: async () => data };
  });
}
beforeEach(() => {
  hasTent = false;
  vi.stubGlobal("fetch", mockFetch());
});
afterEach(() => vi.unstubAllGlobals());
const mount = () =>
  render(
    <MemoryRouter>
      <Environment />
    </MemoryRouter>,
  );
test("empty workspace has no presets and blank user defined targets", async () => {
  mount();
  expect(await screen.findByText(/No tents yet/)).toBeInTheDocument();
  expect(navigation.find((n) => n.title === "Environment")?.path).toBe(
    "/environment",
  );
  expect(screen.getByLabelText("Tent name")).toHaveValue("");
  expect(screen.getByLabelText("Profile name")).toHaveValue("");
  expect(screen.getByLabelText("Temperature minimum (°F)")).toHaveValue(null);
});
test("create tent sends a command key then displays recorded values and warnings", async () => {
  const user = userEvent.setup();
  mount();
  await screen.findByText(/No tents yet/);
  await user.type(screen.getByLabelText("Tent name"), "Boom Room 2");
  await user.click(
    within(screen.getByLabelText("Tent name").closest("form")!).getByRole(
      "button",
      { name: "Save" },
    ),
  );
  expect(
    await screen.findByRole("heading", { name: "Boom Room 2" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Relative humidity: low/)).toBeInTheDocument();
  expect(
    await screen.findByRole("img", {
      name: /Temperature recorded observations/,
    }),
  ).toBeInTheDocument();
  const call = vi
    .mocked(fetch)
    .mock.calls.find(
      ([u, o]) => u === "/api/environment/tents" && o?.method === "POST",
    )!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    name: "Boom Room 2",
    request_key: expect.any(String),
  });
});
test("tent creation works on LAN HTTP without crypto.randomUUID", async () => {
  vi.stubGlobal("crypto", {
    getRandomValues: (bytes: Uint8Array) => {
      for (let i = 0; i < bytes.length; i++) bytes[i] = i + 1;
      return bytes;
    },
  });
  const user = userEvent.setup();
  mount();
  await screen.findByText(/No tents yet/);
  await user.type(screen.getByLabelText("Tent name"), "Boom Room 2");
  await user.click(
    within(screen.getByLabelText("Tent name").closest("form")!).getByRole(
      "button",
      { name: "Save" },
    ),
  );
  expect(
    await screen.findByRole("heading", { name: "Boom Room 2" }),
  ).toBeInTheDocument();
  const call = vi
    .mocked(fetch)
    .mock.calls.find(
      ([u, o]) => u === "/api/environment/tents" && o?.method === "POST",
    )!;
  expect(JSON.parse(String(call[1]?.body)).request_key).toMatch(
    /^[0-9a-f]{32}$/,
  );
});
test("manual readings send missing CO2 as unknown with a UTC observation time", async () => {
  hasTent = true;
  const user = userEvent.setup();
  mount();
  await screen.findByRole("heading", { name: "Boom Room 2" });
  await user.type(screen.getByLabelText("Temperature (°F)"), "70");
  await user.type(screen.getByLabelText("Relative humidity (% RH)"), "88");
  await user.click(
    within(
      screen.getByLabelText("Observed at (local time)").closest("form")!,
    ).getByRole("button", { name: "Save" }),
  );
  await waitFor(() =>
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(
          ([u, o]) => String(u).endsWith("/readings") && o?.method === "POST",
        ),
    ).toBe(true),
  );
  const call = vi
    .mocked(fetch)
    .mock.calls.find(
      ([u, o]) => String(u).endsWith("/readings") && o?.method === "POST",
    )!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    temperature_f: 70,
    humidity: 88,
    co2: null,
    fan: null,
    observed_at: expect.stringMatching(/Z$/),
  });
});
test("reading details preserve original targets equipment notes and navigation", async () => {
  const user = userEvent.setup(),
    correct = vi.fn();
  render(
    <MemoryRouter>
      <ReadingTable
        readings={[reading, { ...reading, id: 2, superseded_by: 3 }]}
        onCorrect={correct}
      />
    </MemoryRouter>,
  );
  await user.click(screen.getByText("Reading #1"));
  expect(screen.getAllByText(/humidity: low/)).toHaveLength(2);
  expect(screen.getAllByRole("link", { name: "FR-1" })[0]).toHaveAttribute(
    "href",
    "/culture-library/fruiting/FR-1",
  );
  await user.click(screen.getByRole("button", { name: "Correct reading #1" }));
  expect(correct).toHaveBeenCalledWith(reading);
  expect(
    screen.queryByRole("button", { name: "Correct reading #2" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Superseded by #3")).toBeInTheDocument();
});
test("network failure offers retry without invented data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Offline")));
  mount();
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Offline");
  vi.stubGlobal("fetch", mockFetch());
  await userEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);
  expect(await screen.findByText(/No tents yet/)).toBeInTheDocument();
});
test("local timestamps round trip and invalid values fail", () => {
  const s = localDateTime("2025-02-01T12:30:00Z");
  expect(localDateTime(observationTime(s))).toBe(s);
  expect(localDateTime(observationTime(s.slice(0, 16)))).toBe(
    s.slice(0, 16) + ":00.000",
  );
  expect(() => observationTime("invalid")).toThrow("valid local");
});
