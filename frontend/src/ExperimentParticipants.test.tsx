import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, beforeEach, afterEach, expect, test } from "vitest";
import ExperimentParticipants from "./components/ExperimentParticipants";
import { blankPlan } from "./experimentApi";
import type { Experiment } from "./experimentApi";
import type { ParticipantPage } from "./experimentParticipants";

const record: Experiment = {
  id: "EX-1",
  category: "substrate",
  scope: "fruiting",
  state: "planned",
  archived: 0,
  revision: 2,
  plan_revision: 2,
  plan: {
    ...blankPlan(),
    title: "Trial",
    primary_variable: "Substrate",
    groups: [
      { id: "EG-A", name: "Control", treatment: "A", control: true },
      { id: "EG-B", name: "Comparison", treatment: "B", control: false },
    ],
  },
  classification: "uncertain",
  classification_basis: "Timing",
  started_at: null,
  treatment_start: null,
  timing_precision: null,
  post_start_amendment: false,
};
let data: ParticipantPage;
let calls: { path: string; body: Record<string, unknown> }[];
let failing = false;
beforeEach(() => {
  calls = [];
  failing = false;
  data = {
    items: [],
    total: 0,
    candidates: [
      {
        fruiting_id: "FR-1",
        batch_id: "GB-1",
        spawn_ids: ["SJ-1"],
        line_ids: ["CL-1"],
        ambiguous: false,
        fingerprint: "original",
      },
    ],
    candidate_total: 1,
    revision: 2,
    plan_revision: 2,
    page: 1,
    page_size: 50,
    rules: [],
    counts: {
      containers: 0,
      treatment_units: 0,
      known_spawn_sources: 0,
      classification_counts: {},
    },
    unit_warning: "Shared sources do not prove independent trials.",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        calls.push({ path, body: JSON.parse(init.body as string) });
        return new Response(
          JSON.stringify(
            failing
              ? { detail: "Provenance changed; reload before confirming" }
              : path.endsWith("creation-allocations")
                ? { allocation: { id: "EA-1" }, revision: 3 }
                : { revision: 3, membership: { id: 1 } },
          ),
          { status: failing ? 409 : 200 },
        );
      }
      if (path.includes("participants"))
        return new Response(JSON.stringify(data));
      if (path.includes("enrollment-history"))
        return new Response(JSON.stringify({ items: [], total: 0 }));
      if (path.includes("library/spawn"))
        return new Response(
          JSON.stringify([
            {
              id: "SJ-1",
              status: "active",
              stage: "ready",
              strain_name: "Oyster",
            },
          ]),
        );
      return new Response(
        JSON.stringify([
          {
            id: "R-1",
            name: "Formula A",
            status: "active",
            recipe_type: "substrate",
            revision: 1,
          },
          {
            id: "R-2",
            name: "Formula B",
            status: "active",
            recipe_type: "substrate",
            revision: 2,
          },
        ]),
      );
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());
function setup(r = record) {
  return render(
    <MemoryRouter>
      <ExperimentParticipants record={r} refresh={vi.fn()} />
    </MemoryRouter>,
  );
}

test("existing container enrollment carries provenance and revision evidence", async () => {
  setup();
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Fruiting container"),
    "FR-1",
  );
  await user.selectOptions(screen.getByLabelText("Assign to group"), "EG-B");
  await user.click(screen.getByRole("button", { name: "Link container" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toMatchObject({
    expected_revision: 2,
    plan_revision: 2,
    group_id: "EG-B",
    fruiting_id: "FR-1",
    fingerprint: "original",
  });
});

test("conflict retains selection and exact retry key", async () => {
  failing = true;
  setup();
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByLabelText("Fruiting container"),
    "FR-1",
  );
  await user.click(screen.getByRole("button", { name: "Link container" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Provenance changed",
  );
  expect(screen.getByLabelText("Fruiting container")).toHaveValue("FR-1");
  await user.click(screen.getByRole("button", { name: "Link container" }));
  expect(calls[0].body.request_key).toBe(calls[1].body.request_key);
});

test("save destination-specific assignments before the consuming creation command", async () => {
  setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Create new" }));
  await user.selectOptions(
    await screen.findByLabelText("Ready spawn source"),
    "SJ-1",
  );
  await user.selectOptions(
    screen.getByLabelText("Substrate recipe for group 1"),
    "R-1",
  );
  await user.selectOptions(
    screen.getByLabelText("Substrate recipe for group 2"),
    "R-2",
  );
  await user.click(
    screen.getByRole("button", { name: "Save assignments before treatment" }),
  );
  expect(
    await screen.findByText(/Assignments saved as EA-1/),
  ).toBeInTheDocument();
  expect(calls[0].body).toMatchObject({
    destinations: [
      { group_id: "EG-A", recipe_id: "R-1", count: 1 },
      { group_id: "EG-B", recipe_id: "R-2", count: 1 },
    ],
  });
  await user.click(
    screen.getByRole("button", { name: "Create assigned containers" }),
  );
  expect(calls[1].body).toMatchObject({ allocation_id: "EA-1" });
  expect(calls[1].path).toBe("/api/experiments/EX-1/fruiting");
});

test("participants distinguish shared sources, repeated observations and correction review", async () => {
  data.items = [
    {
      id: 1,
      fruiting_id: "FR-1",
      unit_id: "EU-1",
      group_id: "EG-A",
      group_name: "Control",
      unit_kind: "container",
      plan_revision: 2,
      classification: "retrospective",
      exposure_start: "2026-01-01",
      exposure_end: null,
      flush_count: 3,
      sources: data.candidates[0],
      evidence: {
        status: "needs_review",
        origin: "lineage",
        review_reason: "Provenance changed; group retained",
      },
    },
  ];
  data.counts = {
    containers: 1,
    treatment_units: 1,
    known_spawn_sources: 1,
    classification_counts: { retrospective: 1 },
  };
  setup();
  const user = userEvent.setup();
  expect(
    await screen.findByText(/3 recorded flushes are repeated observations/),
  ).toBeInTheDocument();
  await user.click(screen.getByText("Review FR-1", { exact: true }));
  await user.selectOptions(screen.getByLabelText("Review decision"), "exclude");
  await user.type(screen.getByLabelText("Review reason"), "Mixed ancestry");
  await user.click(screen.getByRole("button", { name: "Save review" }));
  expect(calls[0].body).toMatchObject({
    decision: "exclude",
    fingerprint: "original",
    reason: "Mixed ancestry",
  });
});

test("conditions setup cannot pretend each container is an independent tent trial", async () => {
  setup({ ...record, category: "conditions" });
  expect(
    await screen.findByText(/must share an existing tent-trial unit/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Create new" }),
  ).not.toBeInTheDocument();
});

test("source rules reference a confirmed source and group", async () => {
  setup();
  const user = userEvent.setup();
  await user.click(
    await screen.findByText("Automatically link downstream fruiting records"),
  );
  await user.selectOptions(screen.getByLabelText("Source type"), "physical");
  await user.type(screen.getByLabelText("Permanent source ID"), "AG-1");
  await user.click(
    screen.getByRole("button", { name: "Confirm automatic association" }),
  );
  expect(calls[0].body).toMatchObject({
    source_kind: "physical",
    source_id: "AG-1",
    group_id: "EG-A",
    plan_revision: 2,
  });
});

test("saved creation assignments survive the parent revision refresh", async () => {
  const view = setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Create new" }));
  await user.selectOptions(
    await screen.findByLabelText("Ready spawn source"),
    "SJ-1",
  );
  await user.selectOptions(
    screen.getByLabelText("Substrate recipe for group 1"),
    "R-1",
  );
  await user.selectOptions(
    screen.getByLabelText("Substrate recipe for group 2"),
    "R-2",
  );
  await user.click(
    screen.getByRole("button", { name: "Save assignments before treatment" }),
  );
  expect(
    await screen.findByText(/Assignments saved as EA-1/),
  ).toBeInTheDocument();
  data = { ...data, revision: 3 };
  view.rerender(
    <MemoryRouter>
      <ExperimentParticipants
        record={{ ...record, revision: 3 }}
        refresh={vi.fn()}
      />
    </MemoryRouter>,
  );
  expect(
    await screen.findByRole("button", { name: "Create assigned containers" }),
  ).toBeInTheDocument();
});
