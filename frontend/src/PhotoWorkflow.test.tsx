import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { FruitingPanel } from "./pages/Fruiting";
import type { FruitingDetail, Harvest } from "./fruitingApi";
import type { LibraryRecord, Photo } from "./libraryApi";
const record = {
  id: "FR-0001",
  kind: "fruiting",
  physical_label: "F-01",
  label_reusable: true,
  label_occupied: true,
  material_type: "tray",
  stage: "colonizing",
  fruiting_stage: "colonizing",
  status: "active",
  lifecycle: "active",
} as LibraryRecord;
const totals = {
  harvest_count: 0,
  wet_grams: null,
  dry_grams: null,
  wet_measured_count: 0,
  dry_measured_count: 0,
};
function mock(stage = "colonizing") {
  const data: FruitingDetail = {
    record: { ...record, fruiting_stage: stage },
    source: null,
    legacy: false,
    run: {
      stage,
      current_flush: 1,
      spawning_date: "2026-01-01",
      recipe_snapshot: null,
      environment_snapshot: null,
      spawn_grams: null,
      substrate_grams: null,
      completed_date: null,
      failed_date: null,
      closing_notes: null,
    },
    harvests: [],
    flushes: [
      {
        number: 1,
        pinning_date: stage === "colonizing" ? null : "2026-01-03",
        pinning_notes: null,
        fruiting_date: null,
        ...totals,
      },
    ],
    environment: null,
    environment_changes: [],
    results: {
      ...totals,
      flushes_with_harvests: 0,
      first_harvest_date: null,
      days_to_first_pinning: null,
      days_to_first_harvest: null,
      cycle_days: null,
    },
  };
  const state = {
    data,
    failFile: "",
    failed: false,
    offline: false,
    offlineOnFailure: false,
    loseRecordResponse: false,
  };
  const photos = new Map<string, Photo[]>();
  const records = new Map<string, unknown>();
  let count = 0;
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = new URL(String(input), "http://test").pathname;
      const response = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), { status });
      if (init?.method === "POST" && init.body instanceof FormData) {
        const file = init.body.get("file") as File;
        if (file.name === state.failFile && !state.failed) {
          state.failed = true;
          if (state.offlineOnFailure) state.offline = true;
          return response({ detail: "Image rejected" }, 422);
        }
        const photo = {
          id: `photo-${++count}`,
          url: `/api/library/photos/photo-${count}/original`,
          thumbnail_url: `/api/library/photos/photo-${count}/thumbnail`,
          is_cover: false,
        } as Photo;
        photos.set(path, [...(photos.get(path) || []), photo]);
        return response(photo, 201);
      }
      if (init?.method === "DELETE") {
        const id = path.split("/").at(-1);
        for (const [key, list] of photos)
          photos.set(
            key,
            list.filter((p) => p.id !== id),
          );
        return new Response(null, { status: 204 });
      }
      if (init?.method === "POST") {
        const payload = JSON.parse(init.body as string);
        if (records.has(payload.request_key))
          return response(records.get(payload.request_key));
        let result: unknown;
        if (path.endsWith("/stage")) {
          if (payload.action === "next_flush") data.run!.current_flush++;
          const number = data.run!.current_flush;
          const newStage =
            payload.action === "complete"
              ? "completed"
              : payload.action === "fruiting"
                ? "fruiting"
                : "pinning";
          data.run!.stage = newStage;
          data.record.fruiting_stage = newStage;
          let flush = data.flushes.find((f) => f.number === number);
          if (!flush) {
            flush = {
              number,
              pinning_date: null,
              pinning_notes: null,
              fruiting_date: null,
              ...totals,
            };
            data.flushes.push(flush);
          }
          if (payload.action === "fruiting") {
            flush.fruiting_date = payload.action_date;
            flush.fruiting_notes = payload.notes;
          } else if (payload.action === "complete") {
            data.run!.completed_date = payload.action_date;
            data.run!.closing_notes = payload.notes;
            data.record.label_occupied = false;
          } else {
            flush.pinning_date = payload.action_date;
            flush.pinning_notes = payload.notes;
          }
          result = data;
        } else {
          const entry = {
            id: `HR-000${data.harvests.length + 1}`,
            fruiting_id: record.id,
            flush_number: data.run!.current_flush,
            revision: 1,
            ...payload,
          } as Harvest;
          data.harvests.push(entry);
          data.run!.stage = "harvest";
          data.record.fruiting_stage = "harvest";
          result = entry;
        }
        records.set(payload.request_key, JSON.parse(JSON.stringify(result)));
        if (state.loseRecordResponse) {
          state.loseRecordResponse = false;
          throw new Error("Record response lost");
        }
        return response(result);
      }
      if (state.offline)
        return response({ detail: "Connection unavailable" }, 503);
      if (path.endsWith("/photos")) return response(photos.get(path) || []);
      if (path.includes("/api/fruiting/records/")) return response(data);
      return response([]);
    });
  return { state, fetch, photos, records };
}
function mount(stage = "colonizing") {
  return render(
    <MemoryRouter>
      <FruitingPanel
        record={{ ...record, fruiting_stage: stage }}
        onSaved={vi.fn()}
      />
    </MemoryRouter>,
  );
}
function file(name: string) {
  return new File(["picture"], name, { type: "image/png" });
}
const stagePosts = (fetch: ReturnType<typeof mock>["fetch"]) =>
  fetch.mock.calls.filter(
    ([path, init]) =>
      String(path).endsWith("/stage") &&
      (init as RequestInit)?.method === "POST",
  );

test("Pinning without photos still saves the date and notes without photo requests", async () => {
  const { fetch, state } = mock();
  mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Mark Pinning" }));
  await user.type(
    screen.getByLabelText("Stage notes (optional)"),
    "First pins",
  );
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Save Grow Status" }),
    ).not.toBeInTheDocument(),
  );
  expect(state.data.flushes[0].pinning_notes).toBe("First pins");
  expect(stagePosts(fetch)).toHaveLength(1);
  expect(
    fetch.mock.calls.some(([, init]) => init?.body instanceof FormData),
  ).toBe(false);
});

test.each([false, true])(
  "inline Pinning photos attach to the returned flush (Next Flush: %s)",
  async (next) => {
    const { fetch } = mock(next ? "harvest" : "colonizing");
    mount(next ? "harvest" : "colonizing");
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: next ? "Next Flush" : "Mark Pinning",
      }),
    );
    await user.upload(screen.getByLabelText("Pinning photos (optional)"), [
      file("pins-one.png"),
      file("pins-two.png"),
    ]);
    await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Save Grow Status" }),
      ).not.toBeInTheDocument(),
    );
    const posts = fetch.mock.calls.filter(
      ([, init]) => init?.body instanceof FormData,
    );
    expect(posts).toHaveLength(2);
    for (const [path] of posts)
      expect(String(path)).toBe(
        `/api/fruiting/records/FR-0001/flushes/${next ? 2 : 1}/pinning/photos`,
      );
    const section = screen
      .getByRole("heading", { name: `Flush ${next ? 2 : 1}` })
      .closest("section")!;
    await waitFor(() =>
      expect(
        within(section).getAllByRole("button", { name: /Open photograph/ }),
      ).toHaveLength(2),
    );
    expect(stagePosts(fetch)).toHaveLength(1);
  },
);

test("two harvests entered with photos keep separate directly visible galleries", async () => {
  const { fetch, state } = mock("fruiting");
  mount("fruiting");
  const user = userEvent.setup();
  for (const name of ["harvest-one.png", "harvest-two.png"]) {
    await user.click(
      await screen.findByRole("button", { name: "Record Harvest" }),
    );
    await user.upload(
      screen.getByLabelText("Harvest photos (optional)"),
      file(name),
    );
    await user.click(screen.getByRole("button", { name: "Save Harvest" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Save Harvest" }),
      ).not.toBeInTheDocument(),
    );
  }
  expect(state.data.harvests).toHaveLength(2);
  const posts = fetch.mock.calls.filter(
    ([, init]) => init?.body instanceof FormData,
  );
  expect(posts.map(([path]) => path)).toEqual([
    "/api/fruiting/harvests/HR-0001/photos",
    "/api/fruiting/harvests/HR-0002/photos",
  ]);
  for (const entry of state.data.harvests) {
    const section = screen
      .getByRole("heading", { name: new RegExp(`Harvest ${entry.id}`) })
      .closest("section")!;
    await waitFor(() =>
      expect(
        within(section).getByRole("button", { name: "Open photograph 1" }),
      ).toBeInTheDocument(),
    );
  }
});

test.each(
  ["pinning", "next_flush", "harvest", "fruiting", "complete"].flatMap((kind) =>
    [false, true].map((offline) => ({ kind, offline })),
  ),
)(
  "$kind photo failure retries only remaining files (history offline: $offline)",
  async ({ kind, offline }) => {
    const initial =
      kind === "fruiting"
        ? "pinning"
        : kind === "complete"
          ? "harvest"
          : kind === "pinning"
            ? "colonizing"
            : kind === "next_flush"
              ? "harvest"
              : "fruiting";
    const { fetch, state } = mock(initial);
    state.failFile = "retry.png";
    state.offlineOnFailure = offline;
    mount(initial);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name:
          kind === "pinning"
            ? "Mark Pinning"
            : kind === "next_flush"
              ? "Next Flush"
              : kind === "fruiting"
                ? "Mark Fruiting"
                : kind === "complete"
                  ? "Finish Grow"
                  : "Record Harvest",
      }),
    );
    await user.upload(
      screen.getByLabelText(
        kind === "harvest"
          ? "Harvest photos (optional)"
          : kind === "fruiting"
            ? "Fruiting photos (optional)"
            : kind === "complete"
              ? "Grow Completed photos (optional)"
              : "Pinning photos (optional)",
      ),
      [file("saved.png"), file("retry.png")],
    );
    await user.click(
      screen.getByRole("button", {
        name: kind === "harvest" ? "Save Harvest" : "Save Grow Status",
      }),
    );
    expect(
      await screen.findByText("retry.png: Image rejected"),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      kind === "harvest"
        ? "Harvest HR-0001 saved."
        : kind === "complete"
          ? "Grow Completed saved."
          : kind === "fruiting"
            ? "Fruiting saved for flush 1."
            : `Pinning saved for flush ${kind === "next_flush" ? 2 : 1}.`,
    );
    expect(
      screen.getByLabelText(
        kind === "harvest" ? "Harvest date *" : "Stage date *",
      ),
    ).toBeDisabled();
    if (offline)
      expect(
        (await screen.findAllByText(/Connection unavailable/)).length,
      ).toBeGreaterThan(0);
    else
      await waitFor(() =>
        expect(
          screen.getByText(
            `Current Status: ${kind === "complete" ? "Completed" : kind === "fruiting" ? "Fruiting" : kind === "harvest" ? "Harvest" : "Pinning"}`,
          ),
        ).toBeInTheDocument(),
      );
    const removal = screen.getByRole("button", { name: "Remove retry.png" });
    expect(removal).toBeEnabled();
    const cycle = screen.getByRole("button", { name: "Current Growing Cycle" });
    await user.click(cycle);
    expect(cycle.closest("details")).not.toHaveAttribute("open");
    await user.click(cycle);
    expect(screen.getByText("retry.png: Image rejected")).toBeInTheDocument();
    state.offline = false;
    await user.click(
      screen.getByRole("button", { name: "Retry remaining photos" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Retry remaining photos" }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.queryAllByText(/Connection unavailable/)).toHaveLength(0),
    );
    const recordPosts = fetch.mock.calls.filter(
      ([path, init]) =>
        init?.method === "POST" &&
        !(init.body instanceof FormData) &&
        (String(path).endsWith("/stage") || String(path).endsWith("/harvests")),
    );
    expect(recordPosts).toHaveLength(1);
    const photoPosts = fetch.mock.calls.filter(
      ([, init]) => init?.body instanceof FormData,
    );
    expect(photoPosts).toHaveLength(3);
    expect(
      photoPosts
        .map(([, init]) => (init!.body as FormData).get("file"))
        .map((v) => (v as File).name),
    ).toEqual(["saved.png", "retry.png", "retry.png"]);
    expect(String(photoPosts[2][0])).toBe(
      kind === "harvest"
        ? "/api/fruiting/harvests/HR-0001/photos"
        : kind === "complete"
          ? "/api/fruiting/records/FR-0001/completion/photos"
          : `/api/fruiting/records/FR-0001/flushes/${kind === "next_flush" ? 2 : 1}/${kind === "fruiting" ? "fruiting" : "pinning"}/photos`,
    );
  },
);

test("a lost harvest response replays its request key before uploading photos", async () => {
  const { fetch, state, records } = mock("fruiting");
  state.loseRecordResponse = true;
  mount("fruiting");
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Record Harvest" }),
  );
  await user.upload(
    screen.getByLabelText("Harvest photos (optional)"),
    file("harvest.png"),
  );
  await user.click(screen.getByRole("button", { name: "Save Harvest" }));
  await screen.findByText("Record response lost");
  expect(
    fetch.mock.calls.filter(([, init]) => init?.body instanceof FormData),
  ).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Save Harvest" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Save Harvest" }),
    ).not.toBeInTheDocument(),
  );
  expect(state.data.harvests).toHaveLength(1);
  expect(records.size).toBe(1);
  const posts = fetch.mock.calls.filter(
    ([path, init]) =>
      String(path).endsWith("/harvests") && init?.method === "POST",
  );
  expect(JSON.parse(posts[0][1]!.body as string).request_key).toBe(
    JSON.parse(posts[1][1]!.body as string).request_key,
  );
});

test("later pinning-photo additions and removals never submit stage changes", async () => {
  const { fetch, state } = mock("pinning");
  mount("pinning");
  const user = userEvent.setup();
  const heading = await screen.findByRole("heading", {
    name: /Pinning — 2026-01-03/,
  });
  const section = heading.closest("section")!;
  await user.click(within(section).getByRole("button", { name: "Add Photos" }));
  await user.upload(
    within(section).getByLabelText("Attach photographs"),
    file("later.png"),
  );
  await within(section).findByRole("button", { name: "Open photograph 1" });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await user.click(within(section).getByRole("button", { name: "Remove" }));
  await waitFor(() =>
    expect(
      within(section).queryByRole("button", { name: "Open photograph 1" }),
    ).not.toBeInTheDocument(),
  );
  expect(state.data.flushes[0].pinning_date).toBe("2026-01-03");
  expect(stagePosts(fetch)).toHaveLength(0);
});

test.each(["fruiting", "complete"])(
  "%s saves with optional photos and exposes a later-edit gallery",
  async (kind) => {
    const initial = kind === "fruiting" ? "pinning" : "harvest";
    const { fetch, state } = mock(initial);
    // Fruiting photos must use the actual current flush, including later flushes.
    state.data.run!.current_flush = 2;
    state.data.flushes.push({ ...state.data.flushes[0], number: 2 });
    mount(initial);
    const user = userEvent.setup();
    const label = kind === "fruiting" ? "Mark Fruiting" : "Finish Grow";
    const name = kind === "fruiting" ? "Fruiting" : "Grow Completed";
    await user.click(await screen.findByRole("button", { name: label }));
    await user.type(
      screen.getByLabelText("Stage notes (optional)"),
      "Journal notes",
    );
    await user.upload(screen.getByLabelText(`${name} photos (optional)`), [
      file("one.png"),
      file("two.png"),
    ]);
    await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
    const heading = await screen.findByRole("heading", {
      name: new RegExp(`${name} — 20`),
    });
    const section = heading.closest("section")!;
    await waitFor(() =>
      expect(
        within(section).getAllByRole("button", { name: /Open photograph/ }),
      ).toHaveLength(2),
    );
    expect(within(section).getByText("Journal notes")).toBeInTheDocument();
    const path =
      kind === "fruiting"
        ? "/api/fruiting/records/FR-0001/flushes/2/fruiting/photos"
        : "/api/fruiting/records/FR-0001/completion/photos";
    expect(
      fetch.mock.calls
        .filter(([, init]) => init?.body instanceof FormData)
        .map(([url]) => url),
    ).toEqual([path, path]);
    const date =
      kind === "fruiting"
        ? state.data.flushes[1].fruiting_date
        : state.data.run!.completed_date;
    await user.click(
      within(section).getByRole("button", { name: "Add Photos" }),
    );
    await user.upload(
      within(section).getByLabelText("Attach photographs"),
      file("later.png"),
    );
    await waitFor(() =>
      expect(
        within(section).getAllByRole("button", { name: /Open photograph/ }),
      ).toHaveLength(3),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await user.click(
      within(section).getAllByRole("button", { name: "Remove" })[0],
    );
    await waitFor(() =>
      expect(
        within(section).getAllByRole("button", { name: /Open photograph/ }),
      ).toHaveLength(2),
    );
    expect(stagePosts(fetch)).toHaveLength(1);
    expect(
      kind === "fruiting"
        ? state.data.flushes[1].fruiting_date
        : state.data.run!.completed_date,
    ).toBe(date);
  },
);

test.each(["fruiting", "complete"])("%s needs no photos", async (kind) => {
  const initial = kind === "fruiting" ? "pinning" : "harvest";
  const { fetch } = mock(initial);
  mount(initial);
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", {
      name: kind === "fruiting" ? "Mark Fruiting" : "Finish Grow",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Save Grow Status" }),
    ).not.toBeInTheDocument(),
  );
  expect(stagePosts(fetch)).toHaveLength(1);
  expect(
    fetch.mock.calls.filter(([, init]) => init?.body instanceof FormData),
  ).toHaveLength(0);
});

test("compact event galleries show three thumbnails and expose all photos and editing on demand", async () => {
  const { fetch } = mock("pinning");
  mount("pinning");
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Mark Fruiting" }),
  );
  await user.upload(screen.getByLabelText("Fruiting photos (optional)"), [
    file("one.png"),
    file("two.png"),
    file("three.png"),
    file("four.png"),
  ]);
  await user.click(screen.getByRole("button", { name: "Save Grow Status" }));
  const heading = await screen.findByRole("heading", { name: /Fruiting — 20/ });
  const section = heading.closest("section")!;
  await waitFor(() =>
    expect(
      within(section).getAllByRole("button", { name: /Open photograph/ }),
    ).toHaveLength(3),
  );
  expect(
    within(section).queryByRole("button", { name: "Remove" }),
  ).not.toBeInTheDocument();
  await user.click(
    within(section).getByRole("button", { name: "Show all 4 photos" }),
  );
  expect(
    within(section).getAllByRole("button", { name: /Open photograph/ }),
  ).toHaveLength(4);
  await user.click(within(section).getByRole("button", { name: "Add Photos" }));
  expect(
    within(section).getAllByRole("button", { name: "Remove" }),
  ).toHaveLength(4);
  expect(
    fetch.mock.calls
      .filter(([, init]) => init?.body instanceof FormData)
      .every(([path]) => String(path).endsWith("/flushes/1/fruiting/photos")),
  ).toBe(true);
});
