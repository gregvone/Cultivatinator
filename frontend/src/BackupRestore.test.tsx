import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BackupRestore from "./components/BackupRestore";
import * as restoreRequest from "./restoreRequest";

const secureRandom = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
beforeEach(() => vi.stubGlobal("crypto", { getRandomValues: secureRandom }));
afterEach(() => vi.unstubAllGlobals());

const code = "12345678-1234-4234-8234-123456789abc";
const backup = {
  id: code,
  filename: "manual-test.zip",
  kind: "manual",
  created_at: "2026-11-01T08:00:00Z",
  size_bytes: 500,
  validation: "verified",
  application_version: "0.1.0",
  migration_revision: "0013_journal_photos",
};
const prepared = {
  stored: backup,
  download_url: `/api/backups/prepared/${code}`,
  filename: "cultivatinator-backup-test.zip",
};
const preview = { ...backup, source: "stored", compatibility: "verified" };
const schedule = {
  enabled: true,
  weekday: 6,
  time: "03:00",
  timezone: "America/New_York",
  retention: 12,
};
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}
function mockServer(
  options: {
    locked?: boolean;
    trusted?: boolean;
    configured?: boolean;
    backups?: (typeof backup)[];
    route?: (
      path: string,
      init?: RequestInit,
    ) => Response | Promise<Response> | undefined;
  } = {},
) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = String(input).replace("/api/backups", "").split("?")[0];
      const custom = options.route?.(path, init);
      if (custom) return custom;
      if (path === "/admin/session")
        return json({
          available: true,
          configured: options.configured ?? true,
          unlocked: !options.locked,
          csrf: "csrf-test",
          ...(options.trusted
            ? {
                auth_mode: "trusted_lan",
                trusted_networks: ["192.168.68.0/24"],
              }
            : {}),
        });
      if (path === "/catalog")
        return json({
          backups: options.backups ?? [],
          storage: { used_bytes: 0, available_bytes: 1e9 },
          schedule: {
            schedule,
            next_run: "2026-11-08T08:00:00Z",
            last_success: null,
            last_failure: null,
          },
          operation: null,
          active: false,
          job: null,
        });
      if (path === "/create") return json(prepared);
      if (path === "/restore/stored") return json(preview);
      return json({});
    });
}
async function ready() {
  await screen.findByRole("button", { name: "Create Backup" });
  await screen.findByText(/Backup storage:/);
}

test("complete backup captures once for both destinations and uses a native browser download", async () => {
  const fetch = mockServer();
  let link: HTMLAnchorElement | undefined;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    link = this;
  });
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(
    await screen.findByText(
      /does not confirm that the file was saved externally/,
    ),
  ).toBeVisible();
  expect(link?.getAttribute("href")).toBe(prepared.download_url);
  expect(link?.download).toBe(prepared.filename);
  const calls = fetch.mock.calls.filter(
    ([path]) => path === "/api/backups/create",
  );
  expect(calls).toHaveLength(1);
  expect(JSON.parse(calls[0][1]?.body as string)).toEqual({
    save: true,
    download: true,
  });
  expect(calls[0][1]?.headers).toMatchObject({ "X-Backup-CSRF": "csrf-test" });
});

test("busy cancellation does not duplicate captures and explains a server copy may have completed", async () => {
  const fetch = mockServer({
    route: (path, init) =>
      path === "/create"
        ? new Promise((_, reject) =>
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            ),
          )
        : undefined,
  });
  render(<BackupRestore />);
  await ready();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(screen.getByRole("button", { name: "Create Backup" })).toBeDisabled();
  expect(screen.getByText(/Application writes wait/)).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Cancel backup preparation" }),
  );
  expect(await screen.findByText(/Backup request cancelled/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Create Backup" })).toBeEnabled();
  expect(
    fetch.mock.calls.filter(([path]) => path === "/api/backups/create"),
  ).toHaveLength(1);
});

test("server errors and selected destinations survive panel collapse and retry", async () => {
  let attempts = 0;
  mockServer({
    route: (path) =>
      path === "/create" && attempts++ === 0
        ? json({ detail: "Insufficient disk space" }, 503)
        : undefined,
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<BackupRestore />);
  await ready();
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("checkbox", { name: "Download backup to my computer" }),
  );
  await user.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Insufficient disk space",
  );
  await user.click(screen.getByRole("button", { name: /Backup & Restore/ }));
  await user.click(screen.getByRole("button", { name: /Backup & Restore/ }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Insufficient disk space",
  );
  expect(
    screen.getByRole("checkbox", { name: "Download backup to my computer" }),
  ).not.toBeChecked();
  await user.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(
    await screen.findByText(/Verified backup saved on Debian/),
  ).toBeVisible();
});

test("first setup protects administration and removes routine Linux restore controls", async () => {
  const fetch = mockServer({
    locked: true,
    configured: false,
    route: (path) =>
      path === "/admin/setup"
        ? json({
            available: true,
            configured: true,
            unlocked: true,
            csrf: "new-csrf",
          })
        : undefined,
  });
  render(<BackupRestore />);
  expect(
    await screen.findByRole("heading", { name: "Set Up Backup Administrator" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Create Backup" }),
  ).not.toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("One-time setup code"),
    "private-setup-code",
  );
  await userEvent.type(
    screen.getByLabelText("Administrator passphrase"),
    "my private admin passphrase",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Set Administrator Passphrase" }),
  );
  await ready();
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/backups/admin/setup"),
  ).toBe(true);
  expect(screen.queryByText(/sudo python3/)).not.toBeInTheDocument();
});

test("manual backup requires at least one selected destination", async () => {
  const fetch = mockServer();
  render(<BackupRestore />);
  await ready();
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Save backup on Debian server" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Download backup to my computer" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(screen.getByRole("alert")).toHaveTextContent("at least one");
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/backups/create"),
  ).toBe(false);
});

test("stored deletion requires a separate explicit confirmation", async () => {
  const fetch = mockServer({ backups: [backup] });
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(
    screen.getByRole("region", { name: "Confirm backup deletion" }),
  ).toBeVisible();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
    false,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm Delete Backup" }),
  );
  await waitFor(() =>
    expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
      true,
    ),
  );
});

test("stored restore verifies first and requires acknowledgement, preserving preview on rejection", async () => {
  const fetch = mockServer({
    backups: [backup],
    route: (path) =>
      path === "/restore/confirm"
        ? json({ detail: "Preview expired; verify again" }, 410)
        : undefined,
  });
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Restore" }));
  const confirmation = await screen.findByRole("region", {
    name: "Confirm cultivation restore",
  });
  expect(within(confirmation).getByText("Server backup")).toBeVisible();
  expect(
    within(confirmation).getByText(/safety backup and original data/),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Restore and Replace Current Data" }),
  ).toBeDisabled();
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/backups/restore/confirm"),
  ).toBe(false);
  await userEvent.click(screen.getByRole("checkbox", { name: /I understand/ }));
  await userEvent.click(
    screen.getByRole("button", { name: "Restore and Replace Current Data" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Preview expired");
  expect(screen.queryByText(/Restore: Reconnecting/)).not.toBeInTheDocument();
});

test("restore reconnects after app downtime and reports the authoritative helper result", async () => {
  let confirmed = false;
  let polls = 0;
  const complete = {
    id: code,
    status: "complete",
    message: "Restore complete and healthy",
  };
  mockServer({
    backups: [backup],
    route: (path) => {
      if (path === "/restore/confirm") {
        confirmed = true;
        return json({ id: code, status: "verifying" });
      }
      if (path === "/restore/status")
        return ++polls === 1
          ? Promise.reject(new TypeError("App restarting"))
          : json({ operation: complete });
      if (path === "/catalog" && confirmed)
        return json({
          backups: [backup],
          storage: { used_bytes: 500, available_bytes: 1e9 },
          schedule: { schedule, next_run: null },
          operation: complete,
        });
      return undefined;
    },
  });
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Restore" }));
  await userEvent.click(
    await screen.findByRole("checkbox", { name: /I understand/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Restore and Replace Current Data" }),
  );
  expect(await screen.findByText("Restore: Reconnecting")).toBeVisible();
  expect(screen.getByText(/detailed progress is unavailable/)).toBeVisible();
  expect(
    await screen.findByText("Restore: Complete", {}, { timeout: 5000 }),
  ).toBeVisible();
  expect(screen.getByText("Restore complete and healthy")).toBeVisible();
}, 10000);

test("schedule defaults and updates include the named time zone and retention", async () => {
  const fetch = mockServer();
  render(<BackupRestore />);
  await ready();
  expect(screen.getByLabelText("Day")).toHaveValue("6");
  expect(screen.getByLabelText("Local time")).toHaveValue("03:00");
  expect(screen.getByLabelText("Time zone")).toHaveValue("America/New_York");
  expect(screen.getByLabelText("Automatic backups to retain")).toHaveValue(12);
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Enable automatic backups" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Save Schedule" }));
  const call = fetch.mock.calls.find(
    ([path]) => path === "/api/backups/schedule",
  );
  expect(JSON.parse(call?.[1]?.body as string)).toEqual({
    ...schedule,
    enabled: false,
  });
});

function mockUpload(result = { ...preview, source: "upload" }) {
  const send = vi.fn();
  vi.stubGlobal(
    "XMLHttpRequest",
    class {
      status = 200;
      responseText = JSON.stringify(result);
      upload = {};
      onload: (() => void) | null = null;
      open = vi.fn();
      setRequestHeader = vi.fn();
      send(file: File) {
        send(file);
        queueMicrotask(() => this.onload?.());
      }
    },
  );
  return send;
}

async function choosePreview(source: "stored" | "upload") {
  if (source === "stored") {
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
  } else {
    await userEvent.click(
      screen.getByRole("button", { name: /Restore from ZIP/ }),
    );
    await userEvent.upload(
      screen.getByLabelText("Backup ZIP"),
      new File(["ZIP"], "backup.zip", { type: "application/zip" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Upload and Verify ZIP" }),
    );
  }
}

test.each(["stored", "upload"] as const)(
  "%s HTTP restore sends a valid stable UUID and exposes structured confirmation errors",
  async (source) => {
    mockUpload();
    const fetch = mockServer({
      backups: [backup],
      route: (path) =>
        path === "/restore/confirm"
          ? json(
              {
                detail: [
                  {
                    loc: ["body", "request_id"],
                    msg: "Injected request validation failure",
                  },
                ],
              },
              422,
            )
          : undefined,
    });
    render(<BackupRestore />);
    await ready();
    expect(globalThis.crypto.randomUUID).toBeUndefined();
    await choosePreview(source);
    await screen.findByRole("region", { name: "Confirm cultivation restore" });
    await userEvent.click(
      screen.getByRole("checkbox", { name: /I understand/ }),
    );
    const confirm = screen.getByRole("button", {
      name: "Restore and Replace Current Data",
    });
    await userEvent.click(confirm);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Restore did not start: request_id: Injected request validation failure",
    );
    expect(alert).toHaveFocus();
    await userEvent.click(confirm);
    const calls = fetch.mock.calls.filter(
      ([path]) => path === "/api/backups/restore/confirm",
    );
    expect(calls).toHaveLength(2);
    const first = JSON.parse(calls[0][1]?.body as string);
    const retry = JSON.parse(calls[1][1]?.body as string);
    expect(first.request_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(retry.request_id).toBe(first.request_id);
    expect(first.preview_id).toBe(code);
  },
);

test.each(["stored", "upload"] as const)(
  "%s restore does not stage or expose confirmation without a valid request ID",
  async (source) => {
    const send = mockUpload();
    vi.spyOn(restoreRequest, "newRestoreRequestId").mockReturnValueOnce("");
    const fetch = mockServer({ backups: [backup] });
    render(<BackupRestore />);
    await ready();
    await choosePreview(source);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "request ID is missing or invalid",
    );
    expect(
      screen.queryByRole("region", { name: "Confirm cultivation restore" }),
    ).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([path]) =>
          path === "/api/backups/restore/stored" ||
          path === "/api/backups/restore/confirm",
      ),
    ).toBe(false);
    expect(send).not.toHaveBeenCalled();
  },
);

test("replacing a visible preview cancels the old preview before staging another", async () => {
  const fetch = mockServer({ backups: [backup] });
  render(<BackupRestore />);
  await ready();
  await choosePreview("stored");
  await screen.findByRole("region", { name: "Confirm cultivation restore" });
  await choosePreview("stored");
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter(
        ([path]) => path === "/api/backups/restore/stored",
      ),
    ).toHaveLength(2),
  );
  const calls = fetch.mock.calls.map(
    ([path, init]) => `${init?.method}:${path}`,
  );
  const cancellation = calls.indexOf(
    `DELETE:/api/backups/restore/preview/${code}`,
  );
  expect(cancellation).toBeGreaterThan(0);
  expect(cancellation).toBeLessThan(
    calls.lastIndexOf("POST:/api/backups/restore/stored"),
  );
});

test("post-upload preparation failure cancels the staged preview and leaves no misleading confirmation or upload control", async () => {
  let catalogs = 0;
  mockUpload();
  const fetch = mockServer({
    route: (path) =>
      path === "/catalog" && ++catalogs > 1
        ? json({ detail: "Could not refresh backups" }, 503)
        : undefined,
  });
  render(<BackupRestore />);
  await ready();
  await choosePreview("upload");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not prepare restore. No restore was started. Could not refresh backups",
  );
  expect(
    fetch.mock.calls.some(
      ([path, init]) =>
        path === `/api/backups/restore/preview/${code}` &&
        init?.method === "DELETE",
    ),
  ).toBe(true);
  expect(
    screen.queryByRole("region", { name: "Confirm cultivation restore" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Cancel upload" }),
  ).not.toBeInTheDocument();
});

test("trusted LAN mode opens immediately, explains network authority and never presents password or lock controls", async () => {
  mockServer({ trusted: true });
  render(<BackupRestore />);
  await ready();
  expect(
    screen.getByRole("heading", { name: "Trusted LAN Mode" }),
  ).toBeVisible();
  expect(
    screen.getByText(/Clients in 192.168.68.0\/24 can administer/),
  ).toBeVisible();
  expect(
    screen.queryByLabelText("Administrator passphrase"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Lock Administration" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Unlock Backup Administration" }),
  ).not.toBeInTheDocument();
});

test("trusted LAN actions renew CSRF automatically without asking for a password", async () => {
  let sessions = 0;
  const fetch = mockServer({
    trusted: true,
    route: (path) =>
      path === "/admin/session"
        ? json({
            available: true,
            configured: true,
            unlocked: true,
            auth_mode: "trusted_lan",
            trusted_networks: ["192.168.68.0/24"],
            csrf: ++sessions === 1 ? "initial" : "renewed",
          })
        : undefined,
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Create Backup" }));
  expect(
    await screen.findByText(/Verified backup saved on Debian/),
  ).toBeVisible();
  const call = fetch.mock.calls.find(
    ([path]) => path === "/api/backups/create",
  );
  expect(call?.[1]?.headers).toMatchObject({ "X-Backup-CSRF": "renewed" });
  expect(sessions).toBe(2);
});

test("expired trusted LAN sessions renew once and retry rejected reads without an unlock screen", async () => {
  let catalogs = 0;
  const fetch = mockServer({
    trusted: true,
    route: (path) =>
      path === "/catalog" && ++catalogs === 1
        ? json({ detail: "Session expired" }, 401)
        : undefined,
  });
  render(<BackupRestore />);
  await ready();
  expect(
    fetch.mock.calls.filter(([path]) => path === "/api/backups/admin/session"),
  ).toHaveLength(2);
  expect(
    screen.queryByLabelText("Administrator passphrase"),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Trusted LAN Mode" }),
  ).toBeVisible();
});

test("unauthorized network access shows a clear denial without offering passwordless administration", async () => {
  mockServer({
    route: (path) =>
      path === "/admin/session"
        ? json(
            {
              detail:
                "The connection address is not in a configured trusted network",
            },
            403,
          )
        : undefined,
  });
  render(<BackupRestore />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "not in a configured trusted network",
  );
  expect(
    screen.queryByRole("button", { name: "Create Backup" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText("Administrator passphrase"),
  ).not.toBeInTheDocument();
});

test("trusted LAN still requires explicit delete and restore confirmation", async () => {
  const fetch = mockServer({ trusted: true, backups: [backup] });
  render(<BackupRestore />);
  await ready();
  await userEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(
    screen.getByRole("button", { name: "Confirm Delete Backup" }),
  ).toBeVisible();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
    false,
  );
  await userEvent.click(screen.getByRole("button", { name: "Keep Backup" }));
  await choosePreview("stored");
  expect(
    await screen.findByRole("button", {
      name: "Restore and Replace Current Data",
    }),
  ).toBeDisabled();
  expect(
    fetch.mock.calls.some(([path]) => path === "/api/backups/restore/confirm"),
  ).toBe(false);
});
