import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BackupRestore from "./components/BackupRestore";
const prepared = {
  download_url: "/api/backups/prepared/12345678-1234-1234-1234-123456789abc",
  filename: "cultivatinator-backup-test.zip",
  size_bytes: 500,
};
test("complete backup prepares once and streams using a native browser download without buffering a ZIP blob", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(prepared), { status: 201 }));
  let link: HTMLAnchorElement | undefined;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    link = this;
  });
  render(<BackupRestore />);
  await userEvent.click(
    screen.getByRole("button", { name: "Download Complete Backup" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "does not confirm that the file was saved externally",
  );
  expect(link?.getAttribute("href")).toBe(prepared.download_url);
  expect(link?.download).toBe(prepared.filename);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/backups/prepare");
  expect(fetch.mock.calls[0][1]?.method).toBe("POST");
});
test("busy backup can be cancelled and pending captures do not duplicate on click", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    (_, init) =>
      new Promise((resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      }),
  );
  render(<BackupRestore />);
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "Download Complete Backup" }),
  );
  expect(
    screen.getByRole("button", { name: "Preparing complete backup…" }),
  ).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Application writes wait",
  );
  await user.click(
    screen.getByRole("button", { name: "Cancel backup preparation" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("cancelled");
  expect(
    screen.getByRole("button", { name: "Download Complete Backup" }),
  ).toBeEnabled();
  expect(fetch).toHaveBeenCalledTimes(1);
});
test("server errors remain clear, panel state retains errors, and retry succeeds", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: "Backup was not created: Insufficient disk space",
        }),
        { status: 503 },
      ),
    )
    .mockResolvedValue(new Response(JSON.stringify(prepared), { status: 201 }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<BackupRestore />);
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "Download Complete Backup" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Insufficient disk space",
  );
  await user.click(screen.getByRole("button", { name: /Backup & Restore/ }));
  await user.click(screen.getByRole("button", { name: /Backup & Restore/ }));
  expect(screen.getByRole("alert")).toHaveTextContent("Retry");
  await user.click(
    screen.getByRole("button", { name: "Download Complete Backup" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "download requested",
  );
});
test("restore exposes host-only validation and explicit maintenance instructions", async () => {
  render(<BackupRestore />);
  await userEvent.click(
    screen.getByRole("button", { name: "Restore safely on Debian" }),
  );
  expect(screen.getByText(/workspace_backup.py verify/)).toBeVisible();
  expect(
    screen.getByText(/sudo python3.*workspace_backup.py restore/),
  ).toBeVisible();
  expect(
    screen.getByText(/Browser-driven restore is not provided/),
  ).toBeVisible();
});
