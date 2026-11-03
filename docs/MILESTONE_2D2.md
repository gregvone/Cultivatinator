# Milestone 2D.2 — Browser Backup, Scheduling & Safe Restore

Revision on `feature/milestone-2d2-backup-restore`, PR #9. Continue the original verified ZIP/restore implementation. No application migration: current head remains `0013_journal_photos`; existing format-1 archives remain compatible. No merge or production deployment is performed by this task.

## Everyday use: Settings → Backup & Restore

Routine operations require no terminal. First unlock backup administration with your passphrase. Initial setup uses the private one-time code printed by the host installer, then establishes your administrator passphrase (at least 12 characters). The main cultivation application still has no account login; backup administration is a separate, focused boundary.

**Create Backup** defaults to **both** Save backup on Debian server and Download backup to my computer. Choose either or both; at least one is required. One consistent verified artifact is used for both destinations. Capture shows busy state and can be cancelled. If cancellation races with a completed server save, refresh the list before creating another backup. Browser download failure does not delete a verified server copy. Use Download on that row to retry.

A native browser download request cannot prove the file was saved externally. Check the browser download manager and retain verified copies outside the server, such as on another computer or external disk. **Same-disk backups do not protect against total disk failure.** ZIPs contain private records and photographs and are not encrypted or digitally signed.

**Stored Backups** lists managed entries newest first: date/time, Automatic/Manual, size, validation status, application version and database revision. Verify checks the entire archive without changing cultivation data. Download streams it normally. Restore verifies and stages a preview before asking for replacement confirmation. Delete requires a separate confirmation and affects only the selected managed archive. Missing, changed or corrupt entries are identified; verify errors remain visible. The storage summary shows managed ZIP usage and available filesystem space. Manual archives remain until explicitly deleted.

**Automatic Weekly Backups** defaults to enabled, Sunday, **03:00 America/New_York**, retaining **12** successful automatic backups. Settings allows changing the day, local time, IANA time zone, enabled state and retention (1–52). The application process runs the schedule without a browser or PC. It shows last automatic success, next scheduled occurrence and last failure, including retention errors. A persisted schedule takes effect prospectively when edited.

After downtime, the latest missed occurrence is captured once; older missed weeks are not replayed. An occurrence has a stable UTC identity. Spring-forward missing times run at the first valid minute after the gap; a repeated fall-back time runs at its first occurrence only. Failed jobs are logged and retried after 15 minutes, including helper-startup failures. A successfully published receipt prevents duplicates even if the process dies before updating schedule bookkeeping. Automatic/manual jobs are serialized. After a new automatic archive is fully verified and published, oldest successful automatic archives beyond retention are pruned. Failed captures never trigger pruning. Manual archives and recovery copies are never automatically pruned; archive deletion/pruning is blocked during restore.

## Browser restoration

Use Restore on a stored row, or expand **Restore from ZIP**, select a ZIP from your computer and choose Upload and Verify ZIP. Upload progress switches to verification when bytes have been sent. Uploaded ZIPs are temporary unless **Keep uploaded ZIP as a manual server backup** is selected. Uploading never starts restoration.

The preview shows date, size, source, application/database versions and verified compatibility. Read the replacement and safety-copy warning, select the explicit acknowledgement, then click **Restore and Replace Current Data**. This action is idempotent: a lost response or retry with the same request key cannot launch a second restore.

Restore request IDs use secure UUID v4 generation through `crypto.getRandomValues`, including HTTP LAN browsers where `crypto.randomUUID` is unavailable. The ID is generated and validated before staging a preview, remains paired with that preview for retries, and is checked again before confirmation. Superseded previews and known previews from unsuccessful preparation are cancelled without deleting stored archives. Errors, including HTTP 422 field details, are announced and focused. Older orphaned previews from failed browser attempts expire after 15 minutes (the helper sweeps every 30 seconds); this correction does not delete backups or change helper authorization, schedules, data or schema.

The restricted helper validates again, creates an independent verified safety backup, fences application writes, stops the existing Compose app, proves SQLite writers stopped, replaces only the four data directories, preserves UID/GID 10001, starts the existing app and checks API/database/version health. It never builds an image or changes source/configuration. Status phases are Verifying, Preparing safety backup, Stopping application, Restoring data, Restarting application, Verifying health, then Complete, Rolled back, Failed or Recovery required.

During actual app downtime the browser says **Reconnecting** and retries automatically; it does not invent detailed progress while the proxying app is offline. After reconnection it retrieves the helper's persisted authoritative outcome. Administrator sessions survive app restart/data restore; if a 30-minute session expires, unlock again to retrieve the result. Reloading Settings after reconnect also retrieves the latest outcome.

Ordinary replacement/startup failures trigger the existing automatic rollback: stop the replacement, retain displaced data, restore original directories, restart/check the original installation. Completion is reported only after health and maintenance release succeed. A helper restart after interruption recovers retained originals where safe. Unresolved recovery blocks further maintenance changes. If the app cannot return, use emergency recovery below; commands are needed only for this disaster case.

## Storage and restore scope

The Git checkout, Compose and data **coexist at `/storage/tv/cultivatinator`**, mounted as `/data`. Only these children are included/replaced:

| Directory | Contents |
| --- | --- |
| `database/` | Complete committed SQLite snapshot and application database content |
| `photos/` | Original photographs and generated thumbnails |
| `files/` | Application-managed persistent files |
| `settings/` | Persistent application settings/files |

Permanent IDs, lineage/provenance, acquisitions, reusable-label history, recipes/snapshots, LC accounting, fruiting stages/flushes/harvest revisions and exact event-photo associations are retained. Empty directories are included. Git, source, `.env`, Compose, dependencies, caches, photo-removal tombstones, transient SQLite sidecars and staging are excluded. **Never replace or archive the entire co-located root as a cultivation-data restore.**

Server archives live in `/storage/tv/cultivatinator/backups/`:

```text
backups/
  manual-20261103T210000Z-<unique-id>.zip
  weekly-20261108T080000Z-<unique-id>.zip
  .control/
    schedule.json
    catalog/<uuid>.json
    uploads/<temporary-uuid>.zip
```

`backups/` is excluded from Git, Docker context and ZIP contents. It is never renamed/replaced during cultivation restore. Filenames are unique and published exclusively, never overwritten. Hidden partials cannot appear as completed entries; a durable receipt and exclusive publication support restart recovery. The catalog exposes only controlled UUID entries with generated names. Stored archives are revalidated before restore; size/mtime changes invalidate cached validation. Catalog/scheduling state stays outside the four restored directories. Upload staging is cleaned on failure, cancellation and restart.

Root-protected administrator/session/restore state lives at `/var/lib/cultivatinator-maintenance/`, outside the app mount. Root-owned helper code is installed at `/opt/cultivatinator-maintenance/`; fixed configuration and a resolved Compose snapshot live under `/etc/cultivatinator-maintenance/`. The helper does not execute app-writable checkout code or Compose configuration. Shared runtime communication is `/run/cultivatinator-maintenance/`, mounted read-only into the app. Existing backups/schedules/credentials survive restoring an older cultivation ZIP. Moving only a ZIP to a new installation requires new administrator/helper setup; secrets and host scheduling are deliberately not included in the cultivation archive.

Recovery operations remain under `/storage/tv/cultivatinator-recovery/<UTC-time>-<id>/`, outside the installation:

| Entry | Meaning |
| --- | --- |
| `pre-restore.zip` | Independently verified safety archive |
| `original/` | Four original directories retained at actual shutdown |
| `failed/` | Displaced replacement directories when rollback occurs |
| `operation.json` | Fsynced installation identity and cutover journal |

Keep recovery files after success as well as failure. The online safety ZIP precedes shutdown; original directories also preserve commits made up to actual stop. Recovery copies are never included in ordinary archives or retention pruning. Their paths are shown with the outcome. Disk usage for recovery/staging is additional to the managed ZIP total.

## Authorization and helper trust boundary

`cultivatinator-maintenance.service` is one host systemd service running a small Python-standard-library helper as root. It has **no TCP listener**. The normal app remains UID/GID `10001:10001`, with dropped capabilities and no Docker socket. The helper has local Docker access, which is effectively host-root authority; root-owned code/configuration, fixed installation targets and the local channel form the trust boundary.

The Unix socket directory is root:10001 `0750`, socket `0660`; a randomly generated channel key is root:10001 `0640`, read-only to the app. Peer UID checks and timestamped, nonce-protected HMAC requests authenticate the channel; the app checks that the server peer is root. Requests have bounded size/concurrency and a strict operation/field allowlist. APIs accept controlled backup/preview UUIDs only, never paths, shell commands, Compose projects or Docker targets. Root copies selected input through pinned `O_NOFOLLOW` directory descriptors into private staging, rejecting symlinks, hard links and special files before reading it. Each destructive helper action independently validates the administrator session, CSRF token and explicit confirmation.

Administrator passphrases use salted scrypt (N=32768, r=8, p=1); plaintext is never stored. A root-held hash of the one-time setup code prevents another LAN visitor claiming an unconfigured installation. Consumed setup codes are removed. Login has per-client/global attempt limits. Random session tokens are stored only as hashes in root-private files; at most 16 sessions, absolute 30-minute expiration, HttpOnly SameSite=Strict cookies scoped to `/api/backups` (Secure when served over HTTPS). CSRF headers and exact-origin/Fetch Metadata checks protect browser changes. Backup downloads, catalog access, deletion, scheduling, upload and restore require authorization. The protected machine capture/freeze endpoints use the local channel credential so scheduling and safety backups do not require interactive login. Tokens/passphrases/request bodies are not logged.

The app still assumes a trusted private network. **Unencrypted HTTP does not protect passphrases/cookies from network interception**; use trusted local access or a properly configured HTTPS reverse proxy. Focused backup administration does not add authentication to the existing cultivation API. Application/host compromise remains outside the protection offered by this boundary; a Docker-capable helper must be treated as privileged software.

## One-time Debian deployment/setup (operator only)

These are instructions for a separately approved deployment, not actions performed by Codex. Preserve an existing verified external backup first. Use the existing checkout and review PR #9. The host needs Python 3.10+ with `sqlite3` and IANA `tzdata`, systemd, Docker Engine/Compose v2 and the current non-root app. No new Python package, database server or Docker service is required. Scheduling runs in the existing single Uvicorn worker. Linux host `/proc` access and a local published app port are required for writer/health checks.

Run each command as a single line on the Debian host:

```bash
cd /storage/tv/cultivatinator && git fetch origin
cd /storage/tv/cultivatinator && git switch feature/milestone-2d2-backup-restore
cd /storage/tv/cultivatinator && git pull --ff-only
sudo python3 /storage/tv/cultivatinator/scripts/install_backup_helper.py install --data-root /storage/tv/cultivatinator --compose-file /storage/tv/cultivatinator/compose.yaml
sudo docker compose -f /storage/tv/cultivatinator/compose.yaml up -d --build --wait
sudo systemctl status cultivatinator-maintenance.service --no-pager
curl --fail http://127.0.0.1:8085/api/health
```

The installer checks the existing data bind, copies only the required standard-library modules/schema/revisions and emergency CLI into root-owned directories, freezes resolved Compose configuration, creates channel/session keys, installs/enables the helper unit and prints a **private one-time browser setup code**. Keep that code privately until consumed. It creates `backups/` if absent with UID/GID 10001; it does not recursively chown or alter source/data. Compose adds only the read-only Unix runtime-directory bind to the app, with `create_host_path: false`; run the installer first. `DATA_DIR` must remain the exact host data root. `MAINTENANCE_DIR` defaults to `/run/cultivatinator-maintenance`; normal deployment needs no override. Existing port 8085, `/data`, UID/GID and single-worker behavior remain.

The helper's resolved snapshot is root-private and uses the existing project/service; normal operations only stop/start that container. Re-run the reviewed installer after helper/schema/configuration upgrades, while no restore is active, then recreate the app if needed. Existing administrator credentials, server archives and schedule are retained. The systemd unit restricts filesystem/kernel access and keeps its runtime-directory inode through service restarts so the app's bind remains connected. It starts after Docker and recreates runtime secrets/socket after host boot. The unit itself needs Debian acceptance; cloud tests run its installed code with real Docker/process checks in a disposable controller, where systemctl installation calls are stubbed because that test container has no systemd.

### Debian acceptance without destructive production tests

1. Check helper service and API health. Open Settings, enter the one-time code, set a private passphrase, then lock/unlock administration. Check that ordinary cultivation still works.
2. Confirm enabled Sunday 03:00 America/New_York / retention 12, last/next status and disk usage. Save a schedule edit, refresh and check persistence; restore the desired schedule afterward.
3. Create Both; check one Manual row, Verify it, finish the browser download and keep an external copy. Also test Server only and Download only. Confirm zero destinations is rejected.
4. Select a stored Restore or upload the downloaded ZIP. Check verified preview metadata and acknowledgement requirement, then **Cancel Restore**. Do not confirm a destructive acceptance restore against the existing Debian cultivation database.
5. Delete only a deliberately disposable manual backup, checking the separate confirmation. Do not remove needed recovery archives. Confirm a normal app restart retains catalog/schedule and requires no PC for scheduling.
6. Exercise full restoration, rollback and interruption only in the disposable suites below or another isolated installation. Inspect cultivation history, reports and photo originals/thumbnails afterward. Existing production data is never an acceptance-test target.

The disposable browser suite requires development pytest/Playwright tooling plus Chromium; these are test dependencies, not helper-runtime dependencies. From a development checkout with those installed and the review image built:

```bash
.venv/bin/python scripts/backup_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/backup_docker_smoke.py
```

`backup_browser_smoke.py` retains its entry point and now runs `backup_browser_restore_smoke.py`. It installs the root-owned helper into a disposable controller with host PID/network visibility and the local Docker socket, binds only the private Unix runtime directory into the test app, and checks stored/uploaded restore, actual app restart, browser reconnection, forced health-failure rollback and abrupt helper exit while `database/` is absent. Test privileges are never added to the production app. The host CLI suite separately preserves original multi-flush/harvest/photo/ownership/rollback coverage. All roots/projects are temporary, never `/storage/tv/cultivatinator`.

## Emergency host recovery only

A power loss or abrupt exit during cutover leaves an fsynced root `.cultivatinator-restore-in-progress.json` marker; application startup refuses initialization/migration before opening missing/mixed directories. Do not remove it or create an empty database. Restarting the helper normally attempts safe recovery from its retained operation journal. If the browser cannot reconnect, inspect:

```bash
sudo systemctl status cultivatinator-maintenance.service --no-pager
sudo journalctl -u cultivatinator-maintenance.service -n 100 --no-pager
sudo systemctl restart cultivatinator-maintenance.service
```

If automatic recovery cannot finish, stop the helper before using the retained-original CLI so two coordinators cannot compete. Replace `OPERATION` with the exact recovery directory printed by the operation/marker; use the root-owned installed CLI and frozen Compose file:

```bash
sudo systemctl stop cultivatinator-maintenance.service
sudo python3 -I /opt/cultivatinator-maintenance/scripts/workspace_backup.py recover /storage/tv/cultivatinator-recovery/OPERATION --data-root /storage/tv/cultivatinator --compose-file /etc/cultivatinator-maintenance/compose.json
sudo systemctl start cultivatinator-maintenance.service
```

The CLI prompts for `REPLACE-PERSISTENT-DATA`, checks installation identity, stops/proves writers stopped, restores originals even if `database/` is temporarily missing, clears only the matching marker after completing the directory set, restarts and checks health. Recovery files remain. If a writer, permissions or filesystem issue blocks recovery, preserve the stopped installation, marker and all recovery files, resolve that specific error and retry. Do not mix database/photos from different restore points. An abrupt exit may leave an unused `cultivatinator-verify-*` sibling; retain it during diagnosis and remove only an identified unused staging directory after recovery.

Emergency standalone ZIP verification and restore remain supported (normally use the browser instead):

```bash
sudo python3 -I /opt/cultivatinator-maintenance/scripts/workspace_backup.py verify /path/to/backup.zip
sudo python3 -I /opt/cultivatinator-maintenance/scripts/workspace_backup.py restore /path/to/backup.zip --data-root /storage/tv/cultivatinator --compose-file /etc/cultivatinator-maintenance/compose.json
```

For a lost passphrase or unused setup code, the explicit host-only reset revokes existing sessions and issues a fresh one-time code. Perform it during maintenance; helper restart may recover an interrupted operation:

```bash
sudo python3 /storage/tv/cultivatinator/scripts/install_backup_helper.py reset-admin --confirm RESET-BACKUP-ADMIN
```

## Archive format, consistency and limits

The existing portable format is unchanged:

```text
manifest.json
database/cultivatinator.sqlite3
photos/...
files/...
settings/...
```

Manifest format/protocol 1 records UTC creation time, application 0.1.0, migration revision, directory inventory and every non-manifest file's size/SHA-256. Generated archives use stored ZIP/ZIP64 members with sorted paths/stable member metadata. Validation requires matching application/head and the trusted actual schema catalog (constraints, indexes, history triggers), not just a manifest migration label. Reflected FK declaration order is normalized. There is no automatic downgrade, migration repair or historical backfill.

The full-request asynchronous mutation gate includes photo writes before commit and photo-removal rollback/cleanup after transactions. Capture shares that gate and a dedicated SQLite BEGIN IMMEDIATE reservation while a separate read-only connection uses SQLite's **online backup API**. Committed WAL contents enter the snapshot without copying live WAL/SHM. Integrity, foreign keys, actual schema and referenced originals/thumbnails are verified before success. Reads remain available; writes wait during capture, then resume before archive transmission. Direct external file edits or concurrent app instances are unsupported; detected file changes abort capture.

Validation rejects absolute/traversal/ambiguous paths, symlinks/special entries, duplicate/case-conflicting/file-directory paths, unsupported/encrypted compression, missing/extra members, malformed versions/manifests, truncated ZIPs and checksum errors. Central directory allocation is bounded before parsing. Limits remain 100,000 entries, 40 GiB archive/upload, 32 GiB total uncompressed, 8 GiB per file, 4 MiB manifest, 16 MiB central directory and expansion ratio 1000; SQLite verification has a timeout. Staging disk/permissions are checked, and incoming data is private/fully verified before cutover. Data root, parent and recovery sibling must share a filesystem for atomic renames; the four live children cannot be symlinks or nested mounts.

Allow ample free space for stored ZIPs, snapshot/verification copies, incoming data and an independent safety ZIP; recovery originals stay on disk. Helper previews expire after 15 minutes and are swept every 30 seconds; active/recovery-required inputs are pinned. Native download tickets remain single-use with five-minute expiry, failure/disconnect cleanup, shutdown cleanup and startup stale-artifact recovery. Uploaded app staging is separate from published entries and cleaned reliably. No backup recursively contains `backups/`, credentials, root helper state or recovery directories. SHA-256 detects corruption, not authenticity; restore only trusted archives.

## Validation coverage

Initial browser revision results: **259 backend tests and 152 frontend tests passed**, production and Docker builds passed, fresh/repeated Alembic upgrades and model drift checks passed, and all seven browser suites passed. The final browser/helper suite exercised the installed private CLI, stored/uploaded restore, real stop/restart/reconnection, forced startup rollback and abrupt helper recovery. Existing lineage/preparation Docker persistence suites and the original complete host-CLI restore suite also passed. One existing Starlette/AnyIO deprecation warning remains; no outstanding test failures. Actual Debian systemd/service acceptance is pending as described above.

HTTP LAN correction: **265 backend tests and 168 frontend tests passed**, together with production/Docker builds and the real browser/helper suite with `crypto.randomUUID` disabled for both stored and uploaded restore. Regression coverage includes UUID version/variant, missing secure randomness, invalid/missing IDs, stable retries, field-level errors, and failed/superseded preview cleanup. The backend still rejects malformed IDs before any restore starts; its existing authorization and cancellation protections are unchanged.

Backend regressions cover existing full cultivation/lineage/recipes/flushes/harvest/photos, WAL and concurrent photo rollback, format attacks, real Unix peer/HMAC/nonce/session/CSRF/rate boundaries, catalog publication recovery, schedule/DST/missed-run backoff, retention/manual protection, upload/preview/confirmation and restore idempotency. UI tests cover destination defaults, native downloads, cancel/error/retry, setup, deletion/restore confirmations and reconnection. Real Docker/browser checks exercise installed helper code, scope/ownership, data/photo persistence, source sentinels, rollback and abrupt helper recovery. Existing cultivation/report/browser suites remain required. No migration/model changes are introduced. Debian functional acceptance remains pending.
