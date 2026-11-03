import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Reports from "./pages/Reports";
import { periodBounds } from "./reportApi";
import type { ReportRecord } from "./reportApi";
import { emptyReport, emptyStats } from "./test-fixtures/reports";
function fixture() {
  const data = emptyReport();
  data.summary = {
    ...emptyStats(),
    completed: 3,
    failed: 1,
    terminal_count: 4,
    failure_rate_percent: "25.000",
    qualifying_containers: 2,
    excluded_incomplete_wet: 1,
    average_wet_grams: "200.000",
    total_known_wet_grams: "480.000",
    distinct_spawn_sources: 1,
    wet_measurement_count: 5,
    harvest_count: 6,
  };
  data.options = {
    strains: [
      { id: "STR-1", name: "Oyster", scientific_name: "Pleurotus ostreatus" },
    ],
    species: ["Pleurotus ostreatus"],
  };
  data.records = [
    {
      id: "FR-0001",
      label: "F-01",
      name: null,
      outcome: "completed",
      outcome_date: "2026-01-20",
      archived: true,
      legacy: false,
      strain_identity: "known",
      line_identity: "known",
      strain_ids: ["STR-1"],
      line_ids: ["CL-1"],
      strain_names: ["Oyster"],
      line_names: ["Test line"],
      spawn_ids: ["SJ-1"],
      species: "Pleurotus ostreatus",
      recipe_id: "RCP-1",
      recipe_name: "Historical substrate",
      recipe_revision: 1,
      harvest_count: 2,
      wet_measurement_count: 2,
      known_wet_grams: "200",
      complete_wet: true,
      known_dry_grams: null,
      complete_dry: false,
      days_to_first_pinning: 2,
      days_to_first_harvest: 6,
      cycle_days: 19,
    } as ReportRecord,
  ];
  data.groups = [
    {
      key: "STR-1",
      name: "Oyster",
      identity: "known",
      ranked: true,
      preliminary: true,
      stats: data.summary,
      record_ids: ["FR-0001"],
      revisions: [],
    },
    {
      key: "unknown",
      name: "Unknown provenance",
      identity: "unknown",
      ranked: false,
      preliminary: true,
      stats: emptyStats(),
      record_ids: [],
      revisions: [],
    },
  ];
  data.flushes = [
    {
      number: 1,
      containers_reached: 3,
      qualifying_containers: 2,
      excluded_incomplete_wet: 1,
      average_wet_grams: "100",
      total_known_wet_grams: "250",
      record_ids: ["FR-0001"],
      qualifying_record_ids: ["FR-0001"],
    },
    {
      number: 2,
      containers_reached: 1,
      qualifying_containers: 0,
      excluded_incomplete_wet: 1,
      average_wet_grams: null,
      total_known_wet_grams: null,
      record_ids: [],
      qualifying_record_ids: [],
    },
  ];
  data.active_records = [
    {
      ...data.records[0],
      id: "FR-0002",
      outcome: "active",
      outcome_date: null,
    },
  ];
  return data;
}
function mount(data = fixture()) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const query = new URL(String(input), "http://test").searchParams;
      const group = (query.get("group_by") || "strain") as typeof data.group_by;
      return new Response(JSON.stringify({ ...data, group_by: group }));
    });
  render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>,
  );
  return fetch;
}
test("empty and unknown yields stay Unknown, with coverage and insufficient-data guidance", async () => {
  mount(emptyReport());
  expect(screen.getByRole("status")).toHaveTextContent("Connecting");
  const card = (
    await screen.findByRole("heading", {
      name: "Average completed-container wet yield",
    })
  ).closest("section")!;
  expect(within(card).getByText("Unknown")).toBeInTheDocument();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Insufficient measured",
  );
  expect(document.querySelector(".report-period")).toHaveTextContent(
    "0 eligible terminal records",
  );
});
test("primary average, partial exclusions, preliminary groups and shared sources are explicit", async () => {
  mount();
  await screen.findByRole("heading", {
    name: "Average completed-container wet yield",
  });
  expect(screen.getByText(/2 fully measured containers/)).toHaveTextContent(
    "1 completed containers excluded",
  );
  expect(screen.getByText(/qualifying containers share/)).toHaveTextContent(
    "1 distinct known spawn sources",
  );
  expect(screen.getAllByText("Preliminary").length).toBeGreaterThan(0);
  const figure = screen
    .getByText("Average measured wet yield per completed container")
    .closest("figure")!;
  expect(within(figure).getByText("Oyster")).toBeInTheDocument();
  expect(
    within(figure).queryByText("Unknown provenance"),
  ).not.toBeInTheDocument();
});
test("recorded zero renders as zero and missing values do not", async () => {
  const data = emptyReport();
  data.summary = {
    ...data.summary,
    completed: 1,
    qualifying_containers: 1,
    average_wet_grams: "0.000",
  };
  mount(data);
  const card = (
    await screen.findByRole("heading", {
      name: "Average completed-container wet yield",
    })
  ).closest("section")!;
  expect(within(card).getByText("0 g")).toBeInTheDocument();
});
test("comparison table and drill-downs keep permanent FR and shared spawn/line links", async () => {
  mount();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", {
      name: /Comparison data & grow records/,
    }),
  );
  expect(
    screen.getByRole("table", { name: /Strain comparisons/ }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "1 grow record(s)" }));
  expect(
    within(screen.getByRole("table", { name: /Strain comparisons/ })).getByRole(
      "link",
      { name: "F-01 · FR-0001" },
    ),
  ).toHaveAttribute("href", "/culture-library/fruiting/FR-0001");
  expect(
    within(screen.getByRole("table", { name: /Strain comparisons/ })).getByRole(
      "link",
      { name: "SJ-1" },
    ),
  ).toHaveAttribute("href", "/culture-library/spawn/SJ-1");
  expect(
    within(screen.getByRole("table", { name: /Strain comparisons/ })).getByRole(
      "link",
      { name: "Test line · CL-1" },
    ),
  ).toHaveAttribute("href", "/culture-library/lines/CL-1");
});
test("filters send explicit inclusive period bounds and reliable species/strain identity", async () => {
  const fetch = mount();
  const user = userEvent.setup();
  await screen.findByRole("heading", {
    name: "Average completed-container wet yield",
  });
  await user.selectOptions(
    screen.getByLabelText("Species / Strain"),
    "strain:STR-1",
  );
  await user.selectOptions(screen.getByLabelText("Time Range"), "custom");
  await user.type(screen.getByLabelText("Start date"), "2026-01-01");
  await user.type(screen.getByLabelText("End date"), "2026-01-31");
  await user.selectOptions(screen.getByLabelText("Group Results By"), "line");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  const params = new URL(String(fetch.mock.calls[1][0]), "http://test")
    .searchParams;
  expect(Object.fromEntries(params)).toEqual({
    group_by: "line",
    strain_id: "STR-1",
    start_date: "2026-01-01",
    end_date: "2026-01-31",
  });
  await screen.findByRole("heading", {
    name: "Genetic culture line performance",
  });
  await user.selectOptions(
    screen.getByLabelText("Species / Strain"),
    "species:Pleurotus ostreatus",
  );
  await user.selectOptions(screen.getByLabelText("Time Range"), "30");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  expect(String(fetch.mock.calls[2][0])).toContain(
    "species=Pleurotus+ostreatus",
  );
});
test("custom reversed dates reveal validation without fetching different data", async () => {
  const fetch = mount();
  const user = userEvent.setup();
  await screen.findByRole("heading", {
    name: "Average completed-container wet yield",
  });
  await user.selectOptions(screen.getByLabelText("Time Range"), "custom");
  await user.type(screen.getByLabelText("Start date"), "2026-02-01");
  await user.type(screen.getByLabelText("End date"), "2026-01-01");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(screen.getByRole("alert")).toHaveTextContent("start on or before");
  expect(fetch).toHaveBeenCalledTimes(1);
});
test("flush samples, outcome denominators and active-date scope stay distinct", async () => {
  mount();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: /Flush performance/ }),
  );
  expect(
    screen.getByText(
      "3 containers reached this flush · 1 excluded for incomplete/no wet measurements",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("table", { name: "Flush measurement coverage" }),
  ).toHaveTextContent("Unknown · n=0");
  await user.click(
    screen.getByRole("button", { name: /Outcomes & active grows/ }),
  );
  expect(
    screen.getByText(/1 \/ \(3 completed \+ 1 failed\)/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/These follow the species\/strain filter/),
  ).toHaveTextContent("not date-filtered");
});
test("historical recipe revisions display saved ingredients and records", async () => {
  const data = fixture();
  data.group_by = "recipe";
  data.groups = [
    {
      ...data.groups[0],
      key: "RCP-1",
      name: "Historical substrate",
      revisions: [
        {
          revision: 1,
          name: "Old formula",
          snapshot: {
            ingredients: [
              { name: "Historical hardwood", quantity: "500", unit: "g" },
            ],
            instructions: "Original instructions",
          },
          stats: data.summary,
          record_ids: ["FR-0001"],
        },
      ],
    },
  ];
  mount(data);
  const user = userEvent.setup();
  await screen.findByRole("heading", {
    name: "Average completed-container wet yield",
  });
  await user.selectOptions(screen.getByLabelText("Group Results By"), "recipe");
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  await user.click(
    await screen.findByRole("button", {
      name: /Comparison data & grow records/,
    }),
  );
  await user.click(
    screen.getByRole("button", { name: "1 saved recipe revision(s)" }),
  );
  await user.click(
    screen.getByRole("button", { name: /Revision 1 — Old formula/ }),
  );
  expect(screen.getByText("Historical hardwood: 500 g")).toBeVisible();
  expect(screen.getByText("Original instructions")).toBeVisible();
});
test("report errors remain errors and retry can recover", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValue(new Response(JSON.stringify(emptyReport())));
  render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
  await userEvent.click(
    screen.getByRole("button", { name: "Retry connection" }),
  );
  await screen.findByRole("heading", {
    name: "Average completed-container wet yield",
  });
  expect(fetch).toHaveBeenCalledTimes(2);
});
test("30/90 day presets use local inclusive calendar dates across year and DST boundaries", () => {
  expect(periodBounds("30", "", "", "2026-01-15")).toEqual({
    start_date: "2025-12-17",
    end_date: "2026-01-15",
  });
  expect(periodBounds("90", "", "", "2026-11-03")).toEqual({
    start_date: "2026-08-06",
    end_date: "2026-11-03",
  });
  expect(periodBounds("all", "", "", "2026-11-03")).toEqual({});
});
