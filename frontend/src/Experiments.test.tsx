import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { vi, beforeEach, afterEach, expect, test } from "vitest";
import Experiments, {
  NewExperiment,
  ExperimentDetail,
} from "./pages/Experiments";
import { blankPlan } from "./experimentApi";
import type { Experiment } from "./experimentApi";

const fixture = (): Experiment => ({
  id: "EX-0001",
  category: "conditions",
  scope: "fruiting",
  state: "draft",
  archived: 0,
  revision: 1,
  plan: {
    ...blankPlan(),
    title: "Humidity trial",
    category: "conditions",
    primary_variable: "Humidity",
    groups: [
      { id: "EG-1", name: "A", treatment: "High humidity", control: true },
      { id: "EG-2", name: "B", treatment: "Lower humidity", control: false },
    ],
  },
  plan_revision: 1,
  classification: "uncertain",
  started_at: null,
  treatment_start: null,
  timing_precision: null,
  post_start_amendment: false,
  classification_basis: "Missing allocations remain uncertain.",
});
let calls: { url: string; body: Record<string, unknown> }[];
let failure = false;
beforeEach(() => {
  calls = [];
  failure = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        calls.push({ url, body: JSON.parse(init.body as string) });
        return new Response(
          JSON.stringify(
            failure
              ? { detail: "Experiment changed; reload before editing" }
              : fixture(),
          ),
          {
            status: failure ? 409 : 201,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/participants"))
        return new Response(
          JSON.stringify({
            items: [],
            total: 0,
            candidates: [],
            candidate_total: 0,
            revision: 1,
            plan_revision: 1,
            rules: [],
            counts: {
              containers: 0,
              treatment_units: 0,
              known_spawn_sources: 0,
              classification_counts: {},
            },
            unit_warning: "Assignment counts do not prove independence.",
          }),
        );
      if (url.includes("/enrollment-history"))
        return new Response(JSON.stringify({ items: [], total: 0 }));
      const data = url.includes("/history")
        ? {
            plans: [
              {
                revision: 1,
                snapshot: fixture().plan,
                reason: "Created draft",
                recorded_at: "2026-01-01",
                committed_at: null,
              },
            ],
            audits: [],
            plan_total: 1,
            audit_total: 0,
            page: 1,
            page_size: 50,
          }
        : url.includes("EX-")
          ? fixture()
          : { items: [], total: 0, page: 1, page_size: 50 };
      return new Response(JSON.stringify(data), {
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());
function setup(path = "/experiments/new") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/experiments" element={<Experiments />} />
        <Route path="/experiments/new" element={<NewExperiment />} />
        <Route path="/experiments/:code" element={<ExperimentDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}
async function question() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Experiment title"), "Humidity trial");
  await user.selectOptions(
    screen.getByLabelText("Experiment category"),
    "conditions",
  );
  await user.type(screen.getByLabelText("Primary variable"), "Humidity");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await user.type(screen.getByLabelText("Group 1 treatment"), "High humidity");
  await user.type(screen.getByLabelText("Group 2 treatment"), "Lower humidity");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  return user;
}

test("all categories, guided setup, multiple groups and advanced settings save", async () => {
  setup();
  expect(screen.getByRole("option", { name: "Substrate" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Genetics" })).toBeInTheDocument();
  const user = await question();
  await user.click(screen.getByText("Advanced scientific settings (optional)"));
  await user.type(
    screen.getByLabelText("Allocation schedule"),
    "Randomize before treatment",
  );
  await user.type(screen.getByLabelText("Minimum readings"), "3");
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body.plan).toMatchObject({
    category: "conditions",
    groups: [{ treatment: "High humidity" }, { treatment: "Lower humidity" }],
    advanced: {
      allocation_schedule: "Randomize before treatment",
      minimum_readings: 3,
    },
  });
  expect(calls[0].body.request_key).toBeTruthy();
});

test("save failures retain entries and identical retry keys", async () => {
  failure = true;
  setup();
  const user = await question();
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Experiment changed",
  );
  await user.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[0].body.request_key).toBe(calls[1].body.request_key);
  await user.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByLabelText("Group 1 treatment")).toHaveValue(
    "High humidity",
  );
});

test("group controls support optional control, adding and removing", async () => {
  setup();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Experiment title"), "Recipe test");
  await user.type(screen.getByLabelText("Primary variable"), "Recipe");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await user.click(screen.getByRole("button", { name: "Add group" }));
  expect(screen.getByRole("group", { name: "Group 3" })).toBeInTheDocument();
  await user.click(screen.getByLabelText("Control group 2"));
  expect(screen.getByLabelText("Control group 1")).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "Remove group 3" }));
  expect(
    screen.queryByRole("group", { name: "Group 3" }),
  ).not.toBeInTheDocument();
});

test("detail commits plan with revision and shows preserved history", async () => {
  setup("/experiments/EX-0001");
  expect(
    await screen.findByRole("heading", { name: "Humidity trial" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/plan alone cannot establish prospective/),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Commit plan" })).toBeDisabled();
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("Action reason"),
    "Original plan ready",
  );
  await user.click(screen.getByRole("button", { name: "Commit plan" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toMatchObject({
    expected_revision: 1,
    action: "plan",
    reason: "Original plan ready",
  });
  await user.click(
    screen.getByRole("button", { name: "Plan and audit history" }),
  );
  expect(await screen.findByText(/Plan 1 · Draft/)).toBeInTheDocument();
});

test("empty and unavailable experiment lists have useful states", async () => {
  setup("/experiments");
  expect(await screen.findByText("No experiments yet.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "New experiment" })).toHaveAttribute(
    "href",
    "/experiments/new",
  );
});

test("loading error can be retried", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(
        new Response(
          JSON.stringify({ items: [], total: 0, page: 1, page_size: 50 }),
        ),
      ),
  );
  setup("/experiments");
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  await userEvent.click(
    screen.getByRole("button", { name: "Retry connection" }),
  );
  expect(await screen.findByText("No experiments yet.")).toBeInTheDocument();
});
