import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import CollapsiblePanel from "./CollapsiblePanel";
import { isRestoreRequestId, newRestoreRequestId } from "../restoreRequest";

type Admin = {
  auth_mode?: "password" | "trusted_lan";
  trusted_networks?: string[];
  available: boolean;
  configured: boolean;
  unlocked: boolean;
  csrf?: string;
  detail?: string;
};
type Schedule = {
  enabled: boolean;
  weekday: number;
  time: string;
  timezone: string;
  retention: number;
};
type Backup = {
  id: string;
  filename: string;
  kind: string;
  created_at: string;
  size_bytes: number;
  validation: string;
  application_version: string;
  migration_revision: string;
};
type Operation = {
  id: string;
  status: string;
  message?: string;
  recovery_operation?: string;
};
type Preview = {
  id: string;
  source: string;
  created_at: string;
  size_bytes: number;
  application_version: string;
  migration_revision: string;
  compatibility: string;
};
type Catalog = {
  backups: Backup[];
  storage: { used_bytes: number; available_bytes: number };
  schedule: {
    schedule: Schedule;
    next_run: string | null;
    last_success: { created_at: string } | null;
    last_failure: { message: string; at: string } | null;
    retry_after?: string | null;
  };
  active: boolean;
  operation: Operation | null;
  job: string | null;
};
const terminal = new Set([
  "complete",
  "rolled_back",
  "failed",
  "recovery_required",
]);
const phases: Record<string, string> = {
  verifying: "Verifying",
  preparing_safety_backup: "Preparing safety backup",
  stopping_application: "Stopping application",
  restoring_data: "Restoring data",
  restarting_application: "Restarting application",
  verifying_health: "Verifying health",
  complete: "Complete",
  rolled_back: "Rolled back",
  recovery_required: "Recovery required",
  failed: "Failed",
};
class AdministrationError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
function size(bytes: number) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KiB`
    : `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}
function date(value?: string | null, timeZone?: string) {
  return value
    ? new Date(value).toLocaleString(
        undefined,
        timeZone ? { timeZone, timeZoneName: "short" } : {},
      )
    : "None recorded";
}

export default function BackupRestore() {
  const [admin, setAdmin] = useState<Admin | null>(null);
  const adminSession = useRef<Admin | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [bootstrap, setBootstrap] = useState("");
  const [save, setSave] = useState(true);
  const [download, setDownload] = useState(true);
  const [retain, setRetain] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<
    (Preview & { requestId: string }) | null
  >(null);
  const [confirmed, setConfirmed] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [deleting, setDeleting] = useState<Backup | null>(null);
  const controller = useRef<AbortController | null>(null);
  const xhr = useRef<XMLHttpRequest | null>(null);
  const pending = useRef(false);
  const errorElement = useRef<HTMLParagraphElement>(null);
  const active = Boolean(operation && !terminal.has(operation.status));
  const disabled = Boolean(
    busy || active || operation?.status === "recovery_required",
  );

  useEffect(() => {
    if (error) {
      errorElement.current?.scrollIntoView?.({ block: "center" });
      errorElement.current?.focus();
    }
  }, [error]);

  function updateAdmin(value: Admin) {
    adminSession.current = value;
    setAdmin(value);
  }
  async function readSession(): Promise<Admin> {
    const response = await fetch("/api/backups/admin/session", {
      cache: "no-store",
      credentials: "same-origin",
    });
    const value = await response.json();
    if (!response.ok)
      throw new Error(
        typeof value?.detail === "string"
          ? value.detail
          : "Could not check backup administration",
      );
    return value as Admin;
  }
  async function renewTrustedSession() {
    const value = await readSession();
    if (
      !value.available ||
      value.auth_mode !== "trusted_lan" ||
      !value.unlocked
    )
      throw new Error(
        value.detail ||
          "Trusted LAN backup administration is unavailable; check the connection and helper configuration.",
      );
    updateAdmin(value);
  }
  async function api<T>(
    path: string,
    options: RequestInit = {},
    retrySession = true,
  ): Promise<T> {
    const response = await fetch(`/api/backups${path}`, {
      ...options,
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Backup-CSRF": adminSession.current?.csrf || "",
        ...options.headers,
      },
    });
    const value = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401) {
        if (adminSession.current?.auth_mode === "trusted_lan") {
          if (retrySession) {
            await renewTrustedSession();
            return api<T>(path, options, false);
          }
        } else if (adminSession.current)
          updateAdmin({ ...adminSession.current, unlocked: false });
      }
      throw new AdministrationError(
        typeof value?.detail === "string"
          ? value.detail
          : Array.isArray(value?.detail)
            ? value.detail
                .map(
                  (issue: { loc?: unknown[]; msg?: string }) =>
                    `${issue.loc?.filter((part) => part !== "body").join(".") || "Request"}: ${issue.msg || "Invalid value"}`,
                )
                .join("; ")
            : `Backup operation failed (HTTP ${response.status}).`,
        response.status,
      );
    }
    return value as T;
  }
  async function refresh() {
    const result = await api<Catalog>("/catalog");
    setCatalog(result);
    setSchedule(result.schedule.schedule);
    setOperation(result.operation);
  }
  useEffect(() => {
    let mounted = true;
    readSession()
      .then((value: Admin) => {
        if (mounted) updateAdmin(value);
      })
      .catch((reason: Error) => {
        if (mounted) {
          updateAdmin({
            available: false,
            configured: false,
            unlocked: false,
            detail: reason.message,
          });
        }
      });
    return () => {
      mounted = false;
      controller.current?.abort();
      xhr.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (admin?.unlocked)
      void refresh().catch((reason: Error) => setError(reason.message));
  }, [admin?.unlocked]); // Session belongs to the helper and survives app restarts.
  useEffect(() => {
    if (!active || !admin?.unlocked) return;
    let disposed = false;
    async function poll() {
      try {
        const value = await api<{ operation: Operation | null }>(
          `/restore/status?operation_id=${operation?.id}`,
        );
        if (disposed) return;
        setReconnecting(false);
        if (value.operation && value.operation.id === operation?.id) {
          setOperation(value.operation);
          if (terminal.has(value.operation.status)) {
            setPreview(null);
            setConfirmed(false);
            await refresh();
          }
        } else {
          setOperation({
            id: operation?.id || "",
            status: "failed",
            message:
              "No restore job was accepted. Current data was not replaced; review the error and retry the confirmed preview.",
          });
        }
      } catch {
        if (!disposed) setReconnecting(true);
      }
    }
    const timer = window.setInterval(() => void poll(), 2000);
    void poll();
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [active, admin?.unlocked]);

  async function perform(
    label: string,
    action: () => Promise<void>,
    duringRestore = false,
  ) {
    if (pending.current || (active && !duringRestore)) return;
    pending.current = true;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      if (adminSession.current?.auth_mode === "trusted_lan")
        await renewTrustedSession();
      await action();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Backup operation failed",
      );
    } finally {
      pending.current = false;
      setBusy("");
    }
  }
  async function unlock(event: FormEvent) {
    event.preventDefault();
    await perform(
      "Unlocking…",
      async () => {
        const result = await api<Admin>(
          admin?.configured ? "/admin/unlock" : "/admin/setup",
          { method: "POST", body: JSON.stringify({ passphrase, bootstrap }) },
        );
        setPassphrase("");
        setBootstrap("");
        updateAdmin(result);
      },
      true,
    );
  }
  function nativeDownload(url: string, filename: string) {
    if (
      !/^\/api\/backups\/(prepared\/[0-9a-f-]{36}|catalog\/[0-9a-f-]{36}\/download)$/.test(
        url,
      )
    )
      throw new Error("Invalid backup download URL");
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
  async function create() {
    if (!save && !download) {
      setError("Choose at least one backup destination.");
      return;
    }
    await perform("Creating and verifying backup…", async () => {
      const abort = new AbortController();
      controller.current = abort;
      try {
        const result = await api<{
          stored: Backup | null;
          download_url: string | null;
          filename?: string;
        }>("/create", {
          method: "POST",
          body: JSON.stringify({ save, download }),
          signal: abort.signal,
        });
        if (result.download_url)
          nativeDownload(
            result.download_url,
            result.filename || "cultivatinator-backup.zip",
          );
        setNotice(
          `${result.stored ? "Verified backup saved on Debian. " : ""}${result.download_url ? "Download requested. Check your browser downloads; this message does not confirm that the file was saved externally. A failed download does not remove the server copy." : "Manual backups remain until you explicitly delete them."}`,
        );
        await refresh();
      } catch (reason) {
        if (abort.signal.aborted) {
          setNotice(
            "Backup request cancelled. Refresh the list to check whether a verified server copy completed before cancellation. You can retry the download from that copy.",
          );
          await refresh();
        } else throw reason;
      } finally {
        controller.current = null;
      }
    });
  }
  async function prepareRestorePreview(
    prepare: () => Promise<Preview>,
    afterPreparation?: () => Promise<void>,
  ) {
    // Fail before staging anything if secure randomness is unavailable. Keep the
    // validated key in the same state as its preview, including on safe retries.
    const requestId = newRestoreRequestId();
    if (!isRestoreRequestId(requestId))
      throw new Error(
        "Restore did not start: the secure request ID is missing or invalid. Verify the backup again.",
      );
    let staged: Preview | undefined;
    try {
      if (preview) {
        await api(`/restore/preview/${preview.id}`, { method: "DELETE" });
        setPreview(null);
        setConfirmed(false);
      }
      staged = await prepare();
      if (
        !isRestoreRequestId(staged?.id) ||
        staged.compatibility !== "verified"
      )
        throw new Error(
          "The server did not return a valid verified restore preview.",
        );
      await afterPreparation?.();
      setConfirmed(false);
      setPreview({ ...staged, requestId });
    } catch (reason) {
      let cleanup = "";
      if (isRestoreRequestId(staged?.id)) {
        try {
          await api(`/restore/preview/${staged.id}`, { method: "DELETE" });
        } catch {
          cleanup =
            " The staged preview could not be cancelled and will expire automatically after 15 minutes.";
        }
      }
      throw new Error(
        `Could not prepare restore. No restore was started. ${reason instanceof Error ? reason.message : "Preview preparation failed."}${cleanup}`,
      );
    }
  }
  async function selectStored(backup: Backup) {
    await perform("Verifying restore backup…", () =>
      prepareRestorePreview(() =>
        api<Preview>("/restore/stored", {
          method: "POST",
          body: JSON.stringify({ id: backup.id }),
        }),
      ),
    );
  }
  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Select a backup ZIP.");
      return;
    }
    await perform("Uploading…", async () => {
      await prepareRestorePreview(async () => {
        try {
          return await new Promise<Preview>((resolve, reject) => {
            const request = new XMLHttpRequest();
            xhr.current = request;
            request.open(
              "POST",
              `/api/backups/restore/upload?retain=${retain}`,
            );
            request.withCredentials = true;
            request.setRequestHeader("Content-Type", "application/zip");
            request.setRequestHeader(
              "X-Backup-CSRF",
              adminSession.current?.csrf || "",
            );
            request.upload.onprogress = (progress) => {
              if (progress.lengthComputable)
                setBusy(
                  progress.loaded === progress.total
                    ? "Verifying uploaded backup…"
                    : `Uploading… ${Math.round((progress.loaded / progress.total) * 100)}%`,
                );
            };
            request.onload = () => {
              try {
                const value = JSON.parse(request.responseText);
                if (request.status < 200 || request.status >= 300)
                  throw new Error(
                    typeof value.detail === "string"
                      ? value.detail
                      : `Upload verification failed (HTTP ${request.status}).`,
                  );
                resolve(value);
              } catch (reason) {
                reject(reason);
              }
            };
            request.onerror = () =>
              reject(
                new Error(
                  "Upload interrupted. No restore was started; retry the upload.",
                ),
              );
            request.onabort = () =>
              reject(new Error("Upload cancelled. No restore was started."));
            request.send(file);
          });
        } finally {
          xhr.current = null;
        }
      }, refresh);
      setFile(null);
    });
  }
  async function restoreGrow() {
    if (!preview || !confirmed) return;
    if (!isRestoreRequestId(preview.requestId)) {
      setError(
        "Restore did not start: the request ID is missing or invalid. Cancel this preview and verify the backup again.",
      );
      return;
    }
    await perform("Starting restore…", async () => {
      // Keep this key on an uncertain response: retry cannot create a second job.
      try {
        const result = await api<Operation>("/restore/confirm", {
          method: "POST",
          body: JSON.stringify({
            preview_id: preview.id,
            request_id: preview.requestId,
            confirmation: "REPLACE-PERSISTENT-DATA",
          }),
        });
        setOperation(result);
        setPreview(null);
      } catch (reason) {
        if (reason instanceof AdministrationError && reason.status < 500)
          throw new Error(`Restore did not start: ${reason.message}`);
        // The helper may have committed the job before the app connection stopped.
        setOperation({
          id: preview.requestId,
          status: "verifying",
          message:
            "Restore request sent. Reconnecting to retrieve the authoritative outcome.",
        });
        setReconnecting(true);
        throw reason;
      }
    });
  }

  return (
    <CollapsiblePanel
      title="Backup & Restore"
      summary="Weekly backups · server storage · safe restore"
      defaultOpen
    >
      <p>
        Protect the committed database, photographs, thumbnails, files and
        settings. Git, source, Compose, .env and existing backups are excluded.
      </p>
      {error && (
        <p role="alert" ref={errorElement} tabIndex={-1}>
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-message">
          {notice}
        </p>
      )}
      {!admin ? (
        <p role="status">Checking backup administration…</p>
      ) : !admin.available ? (
        <>
          <p role="alert">
            {admin.detail || "The maintenance helper is unavailable."}
          </p>
          <p>
            Complete the one-time Debian helper setup described in
            docs/MILESTONE_2D2.md. Routine backup and restore then work here.
          </p>
        </>
      ) : !admin.unlocked ? (
        <form onSubmit={(event) => void unlock(event)} className="backup-form">
          <h3>
            {admin.configured
              ? "Unlock Backup Administration"
              : "Set Up Backup Administrator"}
          </h3>
          {!admin.configured && (
            <label>
              One-time setup code
              <input
                required
                value={bootstrap}
                onChange={(event) => setBootstrap(event.target.value)}
                autoComplete="off"
              />
            </label>
          )}
          <label>
            Administrator passphrase
            <input
              type="password"
              required
              minLength={12}
              maxLength={1024}
              autoComplete={
                admin.configured ? "current-password" : "new-password"
              }
              value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)}
            />
          </label>
          <p className="muted">
            Use at least 12 characters. Administration unlocks for 30 minutes
            and remains separate from cultivation records.
          </p>
          <button className="primary" disabled={Boolean(busy)}>
            {busy ||
              (admin.configured
                ? "Unlock Backup Administration"
                : "Set Administrator Passphrase")}
          </button>
        </form>
      ) : (
        <>
          {admin.auth_mode === "trusted_lan" ? (
            <section
              aria-label="Trusted LAN backup administration"
              className="backup-operation"
            >
              <h3>Trusted LAN Mode</h3>
              <p>
                Clients in {admin.trusted_networks?.join(", ")} can administer
                backups and restore cultivation data without a password. Only
                use this mode on a network where every allowed client is
                trusted. Deleting backups and replacing data still require
                explicit confirmation.
              </p>
            </section>
          ) : (
            <div className="actions">
              <span>Password Mode · Backup administration unlocked</span>
              <button
                disabled={disabled}
                onClick={() =>
                  void perform("Locking…", async () => {
                    await api("/admin/lock", { method: "POST" });
                    updateAdmin({ ...admin, unlocked: false });
                    setCatalog(null);
                  })
                }
              >
                Lock Administration
              </button>
            </div>
          )}
          {busy && (
            <p role="status">
              {busy} Application writes wait while a consistent snapshot or
              maintenance operation is prepared.
            </p>
          )}
          {operation && (
            <section className="backup-operation" aria-label="Restore outcome">
              <h3>
                Restore:{" "}
                {reconnecting
                  ? "Reconnecting"
                  : phases[operation.status] || operation.status}
              </h3>
              <p role="status">
                {reconnecting
                  ? "The application connection is interrupted. Reconnecting automatically; detailed progress is unavailable until it returns. Do not submit another restore."
                  : operation.message ||
                    "Maintenance helper is processing the restore."}
              </p>
              <p className="muted">Operation {operation.id}</p>
              {operation.recovery_operation && (
                <p>
                  Recovery files retained:{" "}
                  <code>{operation.recovery_operation}</code>
                </p>
              )}
              {(reconnecting || operation.status === "recovery_required") && (
                <p>
                  If the application cannot reconnect, preserve recovery files
                  and follow emergency recovery in docs/MILESTONE_2D2.md. On the
                  Debian host, inspect{" "}
                  <code>sudo systemctl status cultivatinator-maintenance</code>.
                  Do not delete the interruption marker or initialize a new
                  database.
                </p>
              )}
            </section>
          )}
          <h3>Create Backup</h3>
          <fieldset disabled={disabled} className="backup-choices">
            <legend>Destination</legend>
            <label>
              <input
                type="checkbox"
                checked={save}
                onChange={(event) => setSave(event.target.checked)}
              />{" "}
              Save backup on Debian server
            </label>
            <label>
              <input
                type="checkbox"
                checked={download}
                onChange={(event) => setDownload(event.target.checked)}
              />{" "}
              Download backup to my computer
            </label>
          </fieldset>
          <div className="actions">
            <button
              className="primary"
              disabled={disabled}
              onClick={() => void create()}
            >
              Create Backup
            </button>
            {controller.current && (
              <button onClick={() => controller.current?.abort()}>
                Cancel backup preparation
              </button>
            )}
            {xhr.current && (
              <button onClick={() => xhr.current?.abort()}>
                Cancel upload
              </button>
            )}
          </div>
          <p className="muted">
            Keep an external copy. Same-disk backups cannot protect against
            total disk failure. Check browser downloads before relying on an
            external copy.
          </p>
          {catalog && (
            <>
              <CollapsiblePanel
                title="Automatic Weekly Backups"
                summary={
                  catalog.schedule.schedule.enabled ? "Enabled" : "Disabled"
                }
                defaultOpen
              >
                <dl className="info-list">
                  <div>
                    <dt>Last successful automatic backup</dt>
                    <dd>{date(catalog.schedule.last_success?.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Next scheduled backup</dt>
                    <dd>
                      {date(
                        catalog.schedule.next_run,
                        catalog.schedule.schedule.timezone,
                      )}{" "}
                      ({catalog.schedule.schedule.timezone})
                    </dd>
                  </div>
                </dl>
                {catalog.schedule.last_failure && (
                  <p role="alert">
                    Last automatic backup failure (
                    {date(catalog.schedule.last_failure.at)}):{" "}
                    {catalog.schedule.last_failure.message}
                    {catalog.schedule.retry_after &&
                      ` Retry after ${date(catalog.schedule.retry_after)}.`}
                  </p>
                )}
                {schedule && (
                  <form
                    className="backup-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void perform("Saving schedule…", async () => {
                        await api("/schedule", {
                          method: "PUT",
                          body: JSON.stringify(schedule),
                        });
                        await refresh();
                        setNotice("Weekly backup schedule saved.");
                      });
                    }}
                  >
                    <fieldset disabled={disabled} className="backup-schedule">
                      <legend>Weekly schedule</legend>
                      <label className="backup-check">
                        <input
                          type="checkbox"
                          checked={schedule.enabled}
                          onChange={(event) =>
                            setSchedule({
                              ...schedule,
                              enabled: event.target.checked,
                            })
                          }
                        />{" "}
                        Enable automatic backups
                      </label>
                      <label>
                        Day
                        <select
                          value={schedule.weekday}
                          onChange={(event) =>
                            setSchedule({
                              ...schedule,
                              weekday: Number(event.target.value),
                            })
                          }
                        >
                          {[
                            "Monday",
                            "Tuesday",
                            "Wednesday",
                            "Thursday",
                            "Friday",
                            "Saturday",
                            "Sunday",
                          ].map((day, index) => (
                            <option key={day} value={index}>
                              {day}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Local time
                        <input
                          type="time"
                          required
                          value={schedule.time}
                          onChange={(event) =>
                            setSchedule({
                              ...schedule,
                              time: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        Time zone
                        <input
                          required
                          value={schedule.timezone}
                          onChange={(event) =>
                            setSchedule({
                              ...schedule,
                              timezone: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        Automatic backups to retain
                        <input
                          type="number"
                          required
                          min={1}
                          max={52}
                          value={schedule.retention}
                          onChange={(event) =>
                            setSchedule({
                              ...schedule,
                              retention: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                    </fieldset>
                    <button disabled={disabled}>Save Schedule</button>
                  </form>
                )}
                <p className="muted">
                  Defaults: Sunday, 3:00 AM America/New_York, latest 12
                  successful automatic backups. One missed occurrence is caught
                  up after startup. Manual and recovery backups are never
                  automatically pruned.
                </p>
              </CollapsiblePanel>
              <CollapsiblePanel
                title="Stored Backups"
                summary={`${catalog.backups.length} backups · ${size(catalog.storage.used_bytes)}`}
                defaultOpen
              >
                <button
                  disabled={disabled}
                  onClick={() => void perform("Refreshing backups…", refresh)}
                >
                  Refresh Backups
                </button>
                <p>
                  Backup storage: {size(catalog.storage.used_bytes)} used ·{" "}
                  {size(catalog.storage.available_bytes)} available
                </p>
                <p className="muted">
                  Server directory: backups/ (retained during restore). Newest
                  first.
                </p>
                <div className="backup-list">
                  {catalog.backups.length === 0 ? (
                    <p>No stored backups yet.</p>
                  ) : (
                    catalog.backups.map((backup) => (
                      <article className="backup-entry" key={backup.id}>
                        <h4>
                          {backup.kind === "weekly" ? "Automatic" : "Manual"} ·{" "}
                          {date(backup.created_at)}
                        </h4>
                        <p>
                          {size(backup.size_bytes)} ·{" "}
                          {backup.validation === "verified"
                            ? "Verified"
                            : backup.validation.replaceAll("_", " ")}{" "}
                          · App {backup.application_version} · Database{" "}
                          {backup.migration_revision}
                        </p>
                        <p className="muted">{backup.filename}</p>
                        <div className="actions">
                          <button
                            disabled={disabled}
                            onClick={() =>
                              void perform(
                                "Verifying stored backup…",
                                async () => {
                                  try {
                                    await api(`/catalog/${backup.id}/verify`, {
                                      method: "POST",
                                    });
                                    setNotice("Stored backup verified.");
                                  } finally {
                                    await refresh();
                                  }
                                },
                              )
                            }
                          >
                            Verify
                          </button>
                          <button
                            disabled={
                              disabled || backup.validation !== "verified"
                            }
                            onClick={() => {
                              nativeDownload(
                                `/api/backups/catalog/${backup.id}/download`,
                                backup.filename,
                              );
                              setNotice(
                                "Download requested. Check browser downloads; the server copy is retained.",
                              );
                            }}
                          >
                            Download
                          </button>
                          <button
                            disabled={
                              disabled || backup.validation !== "verified"
                            }
                            onClick={() => void selectStored(backup)}
                          >
                            Restore
                          </button>
                          <button
                            className="danger"
                            disabled={disabled}
                            onClick={() => setDeleting(backup)}
                          >
                            Delete
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </CollapsiblePanel>
            </>
          )}
          {deleting && (
            <section
              className="backup-confirm"
              aria-label="Confirm backup deletion"
            >
              <h3>Delete Stored Backup?</h3>
              <p>
                {deleting.filename} will be deleted from this server.
                Cultivation records are unaffected.
              </p>
              <div className="actions">
                <button
                  className="danger"
                  disabled={disabled}
                  onClick={() =>
                    void perform("Deleting backup…", async () => {
                      await api(`/catalog/${deleting.id}`, {
                        method: "DELETE",
                        body: JSON.stringify({ confirmation: "DELETE-BACKUP" }),
                      });
                      setDeleting(null);
                      await refresh();
                      setNotice("Selected backup deleted.");
                    })
                  }
                >
                  Confirm Delete Backup
                </button>
                <button disabled={disabled} onClick={() => setDeleting(null)}>
                  Keep Backup
                </button>
              </div>
            </section>
          )}
          <CollapsiblePanel
            title="Restore from ZIP"
            summary="Upload, verify, then confirm"
          >
            <form
              className="backup-form"
              onSubmit={(event) => void upload(event)}
            >
              <label>
                Backup ZIP
                <input
                  type="file"
                  accept=".zip,application/zip"
                  disabled={disabled}
                  onChange={(event) => setFile(event.target.files?.[0] || null)}
                />
              </label>
              <label className="backup-check">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={retain}
                  onChange={(event) => setRetain(event.target.checked)}
                />{" "}
                Keep uploaded ZIP as a manual server backup
              </label>
              <button disabled={disabled || !file}>
                Upload and Verify ZIP
              </button>
            </form>
            <p>
              Uploading never starts restoration automatically. Uploaded files
              are temporary unless you choose to keep a server copy.
            </p>
          </CollapsiblePanel>
          {preview && (
            <section
              className="backup-confirm"
              aria-label="Confirm cultivation restore"
            >
              <h3>Restore This Backup?</h3>
              <dl className="info-list">
                <div>
                  <dt>Backup date</dt>
                  <dd>{date(preview.created_at)}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{size(preview.size_bytes)}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    {preview.source === "stored"
                      ? "Server backup"
                      : "Uploaded ZIP"}
                  </dd>
                </div>
                <div>
                  <dt>Application / database</dt>
                  <dd>
                    {preview.application_version} / {preview.migration_revision}
                  </dd>
                </div>
                <div>
                  <dt>Compatibility</dt>
                  <dd>
                    Verified — integrity, relationships and photos checked
                  </dd>
                </div>
              </dl>
              <p>
                Current cultivation data will be replaced. An independent safety
                backup and original data directories will be retained. Git,
                source, Compose, .env and stored backups stay in place. The app
                will briefly stop and reconnect automatically.
              </p>
              <label className="backup-check">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={disabled}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />{" "}
                I understand that current cultivation data will be replaced.
              </label>
              <div className="actions">
                <button
                  className="danger"
                  disabled={
                    disabled ||
                    !confirmed ||
                    !isRestoreRequestId(preview.requestId)
                  }
                  onClick={() => void restoreGrow()}
                >
                  Restore and Replace Current Data
                </button>
                <button
                  disabled={disabled}
                  onClick={() =>
                    void perform("Cancelling restore preview…", async () => {
                      await api(`/restore/preview/${preview.id}`, {
                        method: "DELETE",
                      });
                      setPreview(null);
                      setConfirmed(false);
                    })
                  }
                >
                  Cancel Restore
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </CollapsiblePanel>
  );
}
