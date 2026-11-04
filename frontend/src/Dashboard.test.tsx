import {
  render,
  screen,
  within,
  waitFor,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import DashboardPreferences from "./components/DashboardPreferences";
import type { DashboardSummary, AttentionItem } from "./api";

const alert: AttentionItem = {
  record_id: "AG-1",
  title: "P-01 · Oyster",
  target: "/culture-library/physical/AG-1",
  severity: "info",
  description: "Marked Ready. Choose a transfer.",
  rule: "ready",
  category: "Ready for action",
  alert_id: "ready:physical:AG-1",
  fingerprint: "a".repeat(64),
  recorded_date: "2026-01-01",
  elapsed_days: 3,
};
const event = {
  record_id: "AG-1",
  title: "P-01 · Oyster",
  target: alert.target,
  event_id: 1,
  event_type: "ready",
  record_type: "physical",
  occurred_at: "2026-01-04T12:00:00Z",
  description: "Marked Ready with earlier cultivation date.",
  archived: true,
};
function fixture(): DashboardSummary {
  return {
    counts: {
      active_cultures: 1,
      spawn_containers: 0,
      fruiting_units: 0,
      open_alerts: 1,
    },
    attention_items: [alert],
    active_cultivation: [
      {
        record_id: "AG-1",
        title: alert.title,
        target: alert.target,
        stage: "ready",
      },
    ],
    recent_activity: [event],
    environmental_observations: [],
    stage_overview: [
      {
        group: "laboratory",
        label: "Laboratory",
        stage: "ready",
        count: 1,
        target: "/laboratory?filter=ready",
      },
    ],
    harvest_summary: {
      start_date: "2026-01-01",
      end_date: "2026-01-30",
      timezone: "America/New_York",
      harvest_count: 2,
      wet_weight_count: 1,
      wet_grams: "100.125",
      fruiting_count: 1,
    },
  };
}
function mount(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}
function mock(initial = fixture()) {
  let data = structuredClone(initial);
  let hidden: AttentionItem[] = [];
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith("/dashboard/attention") && init?.method === "POST") {
        const cmd = JSON.parse(init.body as string);
        if (cmd.action === "restore") {
          data.attention_items = [alert];
          hidden = [];
        } else {
          data.attention_items = [];
          hidden = [
            {
              ...alert,
              suppression: {
                action: cmd.action,
                until: cmd.action === "snooze" ? "2026-01-07T00:00:00Z" : null,
              },
            },
          ];
        }
        data.counts.open_alerts = data.attention_items.length;
        return Response.json({ saved: true });
      }
      if (path.includes("dashboard/summary")) return Response.json(data);
      if (path.includes("dashboard/attention?"))
        return Response.json({
          items: path.includes("hidden=true") ? hidden : data.attention_items,
          total: path.includes("hidden=true")
            ? hidden.length
            : data.attention_items.length,
          page: 1,
          page_size: 25,
        });
      if (path.includes("dashboard/activity"))
        return Response.json({
          items: [event],
          total: 30,
          page: path.includes("page=2") ? 2 : 1,
          page_size: 25,
        });
      if (path.includes("growing"))
        return Response.json([
          {
            id: "AG-1",
            kind: "physical",
            material_type: "agar_plate",
            growth_stage: "ready",
            lifecycle: "active",
            status: "active",
            strain_name: "Oyster",
            physical_label: "P-01",
            created_at: "2026-01-01",
          },
          {
            id: "AG-2",
            kind: "physical",
            material_type: "agar_plate",
            growth_stage: "colonizing",
            lifecycle: "active",
            status: "active",
            strain_name: "Lion",
            created_at: "2026-01-02",
          },
        ]);
      if (path.includes("/api/fruiting"))
        return Response.json([
          {
            id: "FR-1",
            kind: "fruiting",
            material_type: "tray",
            fruiting_stage: "pinning",
            lifecycle: "active",
            stage: "colonizing",
            status: "active",
            created_at: "2026-01-01",
          },
          {
            id: "FR-2",
            kind: "fruiting",
            material_type: "tray",
            fruiting_stage: "fruiting",
            lifecycle: "active",
            stage: "fruiting",
            status: "active",
            created_at: "2026-01-01",
          },
        ]);
      return Response.json([]);
    });
}
test("cards navigate, alerts focus and expand, periods and missing-weight coverage are explicit", async () => {
  mock();
  mount();
  const link = await screen.findByRole("link", { name: /Active Cultures/ });
  expect(link).toHaveAttribute("href", "/laboratory?filter=active");
  expect(
    screen.getByRole("link", { name: /Spawn Containers/ }),
  ).toHaveAttribute("href", "/cultivation?view=spawn&filter=active");
  expect(screen.getByRole("link", { name: /Fruiting Units/ })).toHaveAttribute(
    "href",
    "/cultivation?view=fruiting&fruiting=active",
  );
  const attention = screen.getByRole("region", { name: "Needs Attention" });
  await userEvent.click(
    within(attention).getByRole("button", { name: /Needs Attention/ }),
  );
  await userEvent.click(screen.getByRole("link", { name: /Open Alerts/ }));
  expect(attention).toHaveFocus();
  expect(attention.querySelector("details")).toHaveAttribute("open");
  expect(
    screen.getByRole("link", { name: /Laboratory · Ready/ }),
  ).toHaveAttribute("href", "/laboratory?filter=ready");
  expect(screen.getByText("100.125 g")).toBeInTheDocument();
  expect(
    screen.getByText(/1 of 2 harvests have wet weights/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Today and the preceding 29 days/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Growing Conditions")).not.toBeInTheDocument();
});
test.each([1, 3, 7])(
  "snooze %i days immediately updates count, offers Undo and persists on refresh",
  async (days) => {
    const fetch = mock();
    mount();
    await screen.findByTestId("open_alerts");
    await userEvent.click(
      screen.getByRole("button", {
        name: `Snooze ${days} ${days === 1 ? "day" : "days"}`,
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("open_alerts")).toHaveTextContent("0"),
    );
    expect(screen.getByRole("status")).toHaveTextContent("snoozed");
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(post![1]!.body as string)).toMatchObject({
      days,
      action: "snooze",
      fingerprint: alert.fingerprint,
    });
    fireEvent(window, new Event("focus"));
    await waitFor(() =>
      expect(screen.getByTestId("open_alerts")).toHaveTextContent("0"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(screen.getByTestId("open_alerts")).toHaveTextContent("1"),
    );
  },
);
test("dismissed alerts can be reviewed and restored", async () => {
  mock();
  mount();
  await screen.findByTestId("open_alerts");
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  await waitFor(() =>
    expect(screen.getByTestId("open_alerts")).toHaveTextContent("0"),
  );
  await userEvent.click(
    screen.getByRole("link", { name: "Review snoozed / dismissed alerts" }),
  );
  expect(
    await screen.findByText("Dismissed until a relevant lifecycle change"),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Restore alert" }));
  expect(
    await screen.findByText("No current hidden attention items."),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("link", { name: "Back to Dashboard" }),
  );
  expect(await screen.findByTestId("open_alerts")).toHaveTextContent("1");
});
test("failed alert mutation stays visible and leaves count unchanged", async () => {
  const fetch = mock();
  const original = fetch.getMockImplementation()!;
  fetch.mockImplementation(async (input, init) =>
    init?.method === "POST"
      ? Response.json(
          { detail: "This alert changed. Refresh before acting." },
          { status: 409 },
        )
      : original(input, init),
  );
  mount();
  await screen.findByTestId("open_alerts");
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Refresh before acting",
  );
  expect(screen.getByTestId("open_alerts")).toHaveTextContent("1");
});
test("activity uses actual local timestamp, archived links, pagination and URL record filters", async () => {
  const fetch = mock();
  mount("/activity");
  expect(await screen.findByText("ready")).toBeInTheDocument();
  expect(
    screen.getByText(new Date(event.occurred_at).toLocaleString()),
  ).toHaveAttribute("datetime", event.occurred_at);
  expect(screen.getByText(/Archived record/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: alert.title })).toHaveAttribute(
    "href",
    alert.target,
  );
  await userEvent.click(screen.getByRole("button", { name: "Next page" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([input]) => String(input).includes("page=2")),
    ).toBe(true),
  );
  await userEvent.selectOptions(screen.getByLabelText("Record type"), "spawn");
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([input]) =>
        String(input).includes("record_type=spawn&page=1"),
      ),
    ).toBe(true),
  );
});
test("stage links apply laboratory URL filtering", async () => {
  mock();
  mount("/laboratory?filter=ready");
  expect(await screen.findByText("P-01 · Agar plate")).toBeInTheDocument();
  expect(screen.getByLabelText("Show records")).toHaveValue("ready");
  expect(screen.queryByText(/AG-2/)).not.toBeInTheDocument();
});
test("fruiting card destination hides spawn and filters exact stage", async () => {
  mock();
  mount("/cultivation?view=fruiting&fruiting=pinning");
  expect(await screen.findByRole("link", { name: "FR-1" })).toBeInTheDocument();
  expect(screen.queryByText(/FR-2/)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Growing Spawn" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Show fruiting records")).toHaveValue("pinning");
});
test("preferences validate range and save separate enabled flags", async () => {
  const prefs = Object.fromEntries(
    Object.entries({
      agar_growing: 21,
      spawn_colonizing: 28,
      fruiting_colonizing: 21,
      pinning: 14,
      fruiting: 14,
    }).map(([key, days]) => [key, { days, enabled: true }]),
  );
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_, init) =>
      Response.json(
        init?.method === "PUT" ? JSON.parse(init.body as string) : prefs,
      ),
    );
  render(<DashboardPreferences />);
  const input = await screen.findByLabelText("Pinning threshold (days)");
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: /Attention Preferences/ }),
  );
  expect(input).toHaveAttribute("min", "1");
  expect(input).toHaveAttribute("max", "365");
  await user.clear(input);
  await user.type(input, "30");
  const fieldset = screen.getByRole("group", {
    name: "Agar growing (Germinating)",
  });
  await user.click(within(fieldset).getByRole("checkbox"));
  await user.click(
    screen.getByRole("button", { name: "Save attention preferences" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("saved");
  const body = JSON.parse(
    fetch.mock.calls.find(([, init]) => init?.method === "PUT")![1]!
      .body as string,
  );
  expect(body.pinning.days).toBe(30);
  expect(body.agar_growing.enabled).toBe(false);
});
