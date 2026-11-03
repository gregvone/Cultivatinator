import { emptyReport } from "./test-fixtures/reports";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
const summary = {
  counts: {
    active_cultures: 0,
    spawn_containers: 0,
    fruiting_units: 0,
    open_alerts: 0,
  },
  attention_items: [],
  active_cultivation: [],
  recent_activity: [],
  environmental_observations: [],
};
function mockApi() {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (input) =>
      new Response(
        JSON.stringify(
          String(input).includes("/api/library/") ||
            String(input).includes("/api/preparation/") ||
            String(input).includes("/api/fruiting")
            ? []
            : String(input).includes("/api/reports/")
              ? emptyReport()
              : String(input).endsWith("app/info")
                ? {
                    name: "Cultivatinator",
                    version: "0.1.0",
                    environment: "test",
                    storage: "SQLite",
                  }
                : summary,
        ),
        { status: 200 },
      ),
  );
}
function mount(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}
test("dashboard loads backend zero counts and all empty states", async () => {
  mockApi();
  mount();
  expect(screen.getByRole("status")).toBeInTheDocument();
  for (const key of Object.keys(summary.counts))
    expect(await screen.findByTestId(key)).toHaveTextContent("0");
  for (const text of [
    "No items currently require attention.",
    "No active cultivation records.",
    "No activity recorded yet.",
    "No environmental observations available.",
  ])
    expect(screen.getByText(text)).toBeInTheDocument();
});
test("counts actually use the response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        ...summary,
        counts: { ...summary.counts, active_cultures: 7 },
      }),
    ),
  );
  mount();
  expect(await screen.findByTestId("active_cultures")).toHaveTextContent("7");
});
test("all navigation routes work, including safe settings metadata", async () => {
  mockApi();
  mount();
  const user = userEvent.setup();
  for (const title of [
    "Culture Library",
    "Laboratory",
    "Cultivation",
    "Acquisitions",
    "Reports",
    "Settings",
    "Dashboard",
  ]) {
    await user.click(screen.getByRole("link", { name: title }));
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: title === "Dashboard" ? "Cultivation Command Center" : title,
      }),
    ).toBeInTheDocument();
    if (title === "Laboratory")
      expect(
        screen.getByRole("heading", { level: 2, name: "Growing Cultures" }),
      ).toBeInTheDocument();
    if (title === "Settings")
      expect(await screen.findByText("0.1.0")).toBeInTheDocument();
  }
  await waitFor(() =>
    expect(screen.queryByRole("status")).not.toBeInTheDocument(),
  );
});
test("API failure is understandable and retry recovers", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValue(new Response(JSON.stringify(summary)));
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Check that the application is running",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Retry connection" }),
  );
  expect(await screen.findByTestId("open_alerts")).toHaveTextContent("0");
  expect(fetch).toHaveBeenCalledTimes(2);
});
test("HTTP failure does not masquerade as an empty dashboard", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("{}", { status: 503 }),
  );
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 503");
  expect(screen.queryByTestId("active_cultures")).not.toBeInTheDocument();
});
test("mobile navigation opens and closes on route selection", async () => {
  mockApi();
  mount();
  await userEvent.click(
    screen.getByRole("button", { name: "Open navigation" }),
  );
  expect(
    screen.getByRole("button", { name: "Close navigation" }),
  ).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(screen.getByRole("link", { name: "Acquisitions" }));
  expect(
    screen.getByRole("button", { name: "Open navigation" }),
  ).toHaveAttribute("aria-expanded", "false");
});
