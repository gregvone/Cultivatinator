# Milestone 2D.2 — Complete Backup & Safe Restore

Implemented on `feature/milestone-2d2-backup-restore` for review and Debian acceptance. Do not merge or deploy without approval. No database migration is added; the current head remains `0013_journal_photos`.

## Download a complete backup

Open **Settings → Backup & Restore → Download Complete Backup**. Preparation shows a busy state and can be cancelled. Application writes wait during capture; ordinary reads remain available. Once verified, the ZIP downloads through the browser's normal download manager. Check that the download completed, verify the archive, and retain a copy outside this server, such as on another computer or external disk. A successful click cannot establish that an external copy exists.

The ZIP includes only `database/`, `photos/`, `files/` and `settings/`, with relative paths, original photos and thumbnails. It preserves permanent identities, lineage, acquisitions, labels/history, recipes and snapshots, LC accounting, fruiting stages, flushes, harvest revisions and exact photo associations. Empty directories are retained. Git, application source, Compose, `.env`, dependencies, Docker images, caches, photo-removal tombstones, staging files and unnecessary SQLite sidecars are excluded.

The Debian checkout, Compose configuration and persistent data **coexist at `/storage/tv/cultivatinator`**. Never archive or replace that entire directory as a data-restore operation. The tool replaces only its four application-data children; `.git`, source, `.env`, Compose and unrelated files stay in place. Source and configuration should be maintained separately through the existing Git/configuration workflow.

## Verify on Debian

Dependencies: Linux, Python **3.10+** with its standard `sqlite3` module, the matching complete checkout (including `backend/app/backup_schema.json` and Alembic revisions), and enough temporary disk space to extract the archive privately. No virtualenv, pip package, Node, database server or cloud service is needed. Python's SQLite library must support the current database schema. Verification needs read access to the archive, not root or a stopped application.

Replace `/path/to/backup.zip` with the downloaded file. This is one Bash command:

```bash
python3 /storage/tv/cultivatinator/scripts/workspace_backup.py verify /path/to/backup.zip
```

Expect `VALID: format 1, application 0.1.0, migration 0013_journal_photos, ...; SQLite integrity, foreign keys and photo references verified`. A failure exits nonzero with an actionable error. Verification does not modify the live installation. Do this before relying on a backup and again after copying it to external storage.

Only restore archives from a trusted source. SHA-256 checksums detect damage and missing content; they are not a digital signature or proof of who created an archive. Archives contain private cultivation data and photographs and are not encrypted.

## Restore safely

Restore is an explicit **host maintenance operation**, not a browser action. First verify the backup and arrange downtime. Keep the backup outside the four directories that will be replaced. Use the matching 2D.2 checkout and existing application image/container. The running image must support the complete-backup API so the tool can create its independent safety ZIP; an already stopped installation can be captured offline after writer checks.

Additional requirements: host `sudo`/root, readable host `/proc`, Docker Engine and Compose v2 at the **local `/var/run/docker.sock`**, one existing Compose `app` container, the exact `/data` bind mount, UID/GID `10001:10001`, and a locally reachable published container port 8085 (default host port 8085). Remote Docker contexts are deliberately ignored. Stop other programs that access this database. Do not run multiple application workers or manually edit persistent files during backup or maintenance.

The data root, its parent and the recovery directory must share a filesystem for atomic directory renames. Each of the four data children must be a real directory on that filesystem, not a symlink or nested mount. The tool checks free space and permissions; allow substantial extra space for incoming data, verification and a full independent safety ZIP. Large live downloads also require temporary space inside the application container.

Run this single-line command:

```bash
sudo python3 /storage/tv/cultivatinator/scripts/workspace_backup.py restore /path/to/backup.zip --data-root /storage/tv/cultivatinator --compose-file /storage/tv/cultivatinator/compose.yaml
```

Read the prompt and type exactly **`REPLACE-PERSISTENT-DATA`** to proceed. A different answer cancels before shutdown/replacement. `--confirm REPLACE-PERSISTENT-DATA` exists for deliberate automation and disposable tests; normal interactive use should retain the prompt.

The tool:

1. Validates the entire archive in private sibling staging, including checksums, actual schema, integrity, foreign keys and photo references, before touching live data.
2. Confirms the existing container's bind, user and local port; checks available space and directory permissions; obtains explicit confirmation and a restore-operation lock.
3. Creates and independently verifies `pre-restore.zip` in a new recovery operation directory. For a running application this happens online before shutdown.
4. Stops the existing service through its Compose file. Confirms the container process stopped, obtains the application's lifetime file lease, inspects host process descriptors for open SQLite database/WAL/SHM files, and checks exclusive SQLite access. A failure prevents cutover.
5. Sets incoming ownership to `10001:10001`, directory modes to `0750` and file modes to `0640`. Renames only the four live directories into `original/`, then installs the four staged replacements. A fsynced journal and root interruption marker protect partial cutover.
6. Starts the existing container without rebuilding/recreating it and checks `/api/health` for database connectivity/current migrations plus `/api/app/info` for the matching version.

After success, the output identifies a retained recovery directory such as `/storage/tv/cultivatinator-recovery/20261103T190000Z-012345abcdef`. It contains:

| Entry | Purpose |
| --- | --- |
| `pre-restore.zip` | Independent, verified recovery archive created before replacement |
| `original/` | Original four directories at actual shutdown, including commits after the online safety snapshot |
| `operation.json` | Fsynced state and installation identity for interrupted recovery |
| `failed/` | Replacement directories retained if rollback occurs |

**Keep the recovery directory and original download.** Success never deletes them. The independent online ZIP and the original shutdown directories can represent slightly different times; originals preserve every commit up to actual stop. Recovery directory defaults to a sibling named `<data-root>-recovery`; `--recovery-dir /another/sibling` is available on the same filesystem, outside the installation. Recovery files are host-root protected. They are not automatically rotated or deleted.

After restore, check Settings, Culture Library, provenance, fruiting journals, harvests and original/thumbnail photographs in the browser before accepting the result. A restore intentionally returns the four directories to the chosen backup's contents.

## Failed or interrupted restore

Ordinary cutover errors, failed health checks, Ctrl-C and SIGTERM trigger automatic rollback where possible. The tool stops the replacement app, retains replacement directories in `failed/`, puts original directories back, restarts and checks the original installation. It reports failure even when rollback succeeds. Read the error and retain all recovery files.

SIGKILL or power loss cannot run cleanup. A root `.cultivatinator-restore-in-progress.json` marker during incomplete replacement makes application startup fail **before storage initialization or migrations**, preventing initialization of a missing database directory. Do not remove the marker, delete recovery files or attempt to create a blank database. If interrupted before cutover, originals are still live; the journal remains useful for diagnosis.

Use the operation directory printed by the failed restore (or identified by the marker), replacing `OPERATION` below:

```bash
sudo python3 /storage/tv/cultivatinator/scripts/workspace_backup.py recover /storage/tv/cultivatinator-recovery/OPERATION --data-root /storage/tv/cultivatinator --compose-file /storage/tv/cultivatinator/compose.yaml
```

Confirm `REPLACE-PERSISTENT-DATA`. Recovery validates the journal's installation identity, stops the app, repeats writer/lease checks, restores retained original directories even when `database/` is temporarily absent, removes the matching interruption marker after completing the directory set, restarts and verifies health. It retains recovery files and displaced incoming data. If a writer, permissions problem or filesystem error blocks recovery, leave the application stopped and preserve the marker, operation directory and backup; resolve that specific error before retrying. Do not manually combine individual databases/photos from different restore points.

Hard termination can leave an unused `cultivatinator-verify-*` staging sibling. Retain it while diagnosing the operation; remove only an identified unused staging directory after successful recovery. The tool does not follow arbitrary journal paths to delete files. No routine recovery command moves or removes the installation root.

## Archive contract and compatibility

```text
manifest.json
database/
database/cultivatinator.sqlite3
photos/...
files/...
settings/...
```

ZIP members are sorted with stable member metadata; the manifest includes a real UTC creation timestamp. Generated ZIPs use stored entries because photographs are already compressed. ZIP64 is supported within enforced limits. `manifest.json` includes `format_version`, application name/version, migration revision, restore protocol/database/roots compatibility metadata, sorted directory inventory, and per-file byte size and SHA-256. The manifest inventories every non-manifest file; extra or missing members fail verification.

The verifier requires format/protocol **1**, application **0.1.0**, the checkout's single Alembic head **0013_journal_photos**, and the exact compatible schema catalog in `backup_schema.json` (including constraints, indexes and triggers). Foreign-key declaration ordering is normalized to account for Alembic's reflected constraint ordering; definitions remain checked. Manifest revision alone is insufficient. No automatic migration, downgrade, schema repair or historical backfill occurs during validation. Use a matching checkout/image; future schema releases must deliberately update their compatibility contract.

Verification bounds: 100,000 ZIP entries, 40 GiB archive, 32 GiB total uncompressed data, 8 GiB per file, 4 MiB manifest, 16 MiB central directory, and maximum expansion ratio 1000. SQLite checks also have a time bound. Oversized workspaces fail explicitly rather than yielding an unsupported archive. The ZIP directory is bounded before Python builds its member list. Validation rejects absolute/traversal/ambiguous paths, backslashes, drive-style paths, symlinks/special files, encrypted/unsupported entries, duplicates/case conflicts, file/directory conflicts, extra/missing entries, truncated ZIP structures and checksum mismatches. Files are streamed into exclusive private staging files; untrusted ZIP permissions and extraction paths are never applied to live storage.

## Consistency and temporary storage

`MutationGate` surrounds each complete mutating HTTP request, including file writes before DB commit and photo-removal rollback/cleanup after a transaction. Backup capture takes the same asynchronous gate. A dedicated SQLite `BEGIN IMMEDIATE` writer reservation also blocks external SQLite writers while the separate read-only source connection uses **SQLite's online backup API**. The snapshot includes committed WAL contents without copying live database/WAL/SHM files. Verification checks SQLite integrity, foreign keys, actual schema and all referenced originals/thumbnails before success. The snapshot, photos, files and settings are inventoried while mutations remain blocked. Direct external filesystem edits are unsupported; detected file changes abort capture.

`POST /api/backups/prepare` returns a single-use opaque download URL; `GET /api/backups/prepared/{token}` streams it natively. Tickets expire after five minutes and are swept every 15 seconds; `DELETE` cancels an unused ticket. `GET /api/backups/download` supports the host tool's direct streaming capture. It accepts no filesystem-path parameters. Temporary artifacts live outside the four backed-up directories in a private OS temporary directory, are removed after streaming (including send errors), capture failures/cancellation and shutdown, and abandoned capture artifacts are cleaned on next startup under the process lease. A disconnected request just after preparation can leave its unused ticket until expiry. Browser-native download errors are visible in the browser download manager and may require a new backup request.

The lifetime OS file lease enforces one application process per data root. Root lock files and the interruption marker are reserved maintenance files, excluded from archives and Git/Docker context. No database tables, photo relationships, original domain records or migrations change. The mutation gate serializes writes in this existing single-user topology; reads and transmission of an already prepared archive do not hold it. There is no new authentication, backup daemon, scheduled job, remote storage or restore API.

## Validation

Cloud validation: **233 backend tests and 147 frontend tests passed**, production frontend and Docker image builds passed, fresh/repeated Alembic upgrades and `alembic check` passed with no drift, and all seven browser suites passed (library, lineage, Quick Create, preparation, fruiting, reports and backup). The real Docker restore smoke passed successful restore, failed-startup rollback and abrupt-process recovery. One existing Starlette/AnyIO deprecation warning remains; there are no outstanding test failures. Debian functional acceptance remains pending.

All restore tests use disposable directories/containers, never Debian production data. Backend tests cover empty/populated snapshots, lineage and multi-flush/harvest/photo histories, WAL, upload and removal rollback concurrency, cancellation, archive attacks/limits, disk failures, one-shot tickets, startup fencing, four-directory replacement, retained independent recovery and rollback. Frontend tests cover native downloads, busy/cancel/error/retry and maintenance instructions.

Run from the checkout with the normal development dependencies installed:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/backup_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/backup_docker_smoke.py
```

Run each command from the indicated directory; the two script commands start at repository root. Browser tooling is the existing optional Playwright setup. The Docker smoke expects the locally built `cultivatinator:milestone-2d2` image, Docker CLI/Compose, local socket and a `python:3.12` controller image. Its temporary root controller uses host networking/process visibility and Docker access to exercise actual host-root ownership and process checks; the app remains UID/GID 10001. It tests complete restore, forced startup-failure rollback, abrupt exit with missing live `database/`, recovery, retrieved original/thumbnail photos, files/settings persistence, and byte-identical `.git`/source/Compose/`.env` sentinels. These test privileges are not added to application Compose.

Existing library, lineage, Quick Create, preparation, fruiting and reports browser suites remain applicable. The preparation smoke now opens the existing collapsed recipe secondary-details panel before checking edited notes. No production deployment or merge is part of this milestone.
