import { useEffect, useRef, useState } from "react";
import CollapsiblePanel from "./CollapsiblePanel";
export default function BackupRestore() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function download() {
    if (busy || controller.current) return;
    setBusy(true);
    setError("");
    setNotice("");
    const pending = new AbortController();
    controller.current = pending;
    try {
      const response = await fetch("/api/backups/prepare", {
        method: "POST",
        signal: pending.signal,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : `Backup failed (HTTP ${response.status}).`,
        );
      }
      const result = await response.json();
      if (
        !/^\/api\/backups\/prepared\/[0-9a-f-]{36}$/.test(
          result.download_url,
        ) ||
        typeof result.filename !== "string"
      )
        throw new Error("The server did not provide a valid backup download.");
      const link = document.createElement("a");
      link.href = result.download_url;
      link.download = result.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setNotice(
        "Backup prepared and download requested. Check your browser downloads, then retain a copy outside this server. This message does not confirm that the file was saved externally.",
      );
    } catch (reason) {
      if (pending.signal.aborted)
        setNotice("Backup preparation cancelled. You can retry.");
      else
        setError(
          reason instanceof Error
            ? reason.message
            : "Backup could not be prepared.",
        );
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }
  return (
    <CollapsiblePanel
      title="Backup & Restore"
      summary="Complete workspace ZIP · local backups"
      defaultOpen
    >
      <p>
        Download the committed database, original photos, thumbnails, files and
        settings. Source code, .git, Docker configuration and .env are excluded.
      </p>
      <div className="actions">
        <button
          className="primary"
          disabled={busy}
          onClick={() => void download()}
        >
          {busy ? "Preparing complete backup…" : "Download Complete Backup"}
        </button>
        {busy && (
          <button onClick={() => controller.current?.abort()}>
            Cancel backup preparation
          </button>
        )}
      </div>
      {busy && (
        <p role="status">
          Preparing and verifying a consistent snapshot. Application writes wait
          while it is captured; the download then streams through your browser.
        </p>
      )}
      {error && (
        <p role="alert">{error} Retry Download Complete Backup when ready.</p>
      )}
      {notice && (
        <p role="status" className="success-message">
          {notice}
        </p>
      )}
      <p className="muted">
        Keep an external copy and verify it before relying on it. Prepared
        download links are single-use and expire after five minutes; temporary
        server files are removed after download or cancellation.
      </p>
      <CollapsiblePanel title="Restore safely on Debian" level={3}>
        <p>
          Restore is a host maintenance operation. Use the matching checkout and
          image. Validate first; the tool asks for explicit replacement
          confirmation, saves a recovery copy, stops the existing app, replaces
          only database/, photos/, files/ and settings/, and checks startup. The
          Git checkout and Compose configuration stay in place.
        </p>
        <p>Verification (replace the archive filename):</p>
        <pre className="backup-command">
          python3 /storage/tv/cultivatinator/scripts/workspace_backup.py verify
          /path/to/backup.zip
        </pre>
        <p>Restore, with an interactive confirmation:</p>
        <pre className="backup-command">
          sudo python3 /storage/tv/cultivatinator/scripts/workspace_backup.py
          restore /path/to/backup.zip
        </pre>
        <p>
          Retain the recovery directory printed by the tool. If interrupted,
          follow docs/MILESTONE_2D2.md to recover the retained originals.
          Browser-driven restore is not provided.
        </p>
      </CollapsiblePanel>
    </CollapsiblePanel>
  );
}
