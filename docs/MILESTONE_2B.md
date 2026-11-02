# Milestone 2B — lineage, acquisitions and grow provenance

Current behavior and the user-confirmed co-located Debian deployment layout are described in [Milestone 2C.2](MILESTONE_2C2.md). Earlier deferred-operation and separate/unknown checkout-location descriptions in this historical milestone document do not override 2C.2.


The cloud implementation checkout is `/workspace/Cultivatinator`. The Debian production data directory is **`/storage/tv/cultivatinator`**. The production checkout and Dockge/Compose configuration directories have not been inspected and must not be assumed to match either path. No production server was accessed or changed.

Current navigation is described in [Milestone 2C.1](MILESTONE_2C1.md): outside acquisitions now live in Inventory, and the catalog is a reference area. The following describes the underlying 2B functionality; no 2B data or API was replaced.

## Registration and navigation

Use **Receive Acquisition** in Culture Library or Cultivation. Select LC syringe/jar, agar plate/slant, spores, colonized spawn jar/bag, ready-to-fruit bag/block, or the existing other-culture/spore options. Choose an existing strain, create one inline, or leave it unknown. Review preserves values with Back. Supplier, reference, batch, date, quantity, notes and location are optional; attach photographs after creation on individual record detail pages. Other fruiting container types are available in grow registration.

Established acquired mycelium uses a compatible existing culture line or creates an independent acquired line. Spores create only a spore source. Spawn defaults to **Ready**, with **Colonizing** available; there is no required earlier preparation/inoculation date. Every spawn jar/bag has an SJ/SB ID. Acquired fruiting material creates one **acquired** GB batch and independently identified FR containers, linked to an acquired line. No substrate recipe, external spawn source or preparation event is invented. Material supplier/batch metadata can differ from the historical line acquisition. Culture quantities remain initial measurements, not balances.

Use **Register Grow Provenance** for a user-prepared batch. Select known spawn sources and an allocation mode:

- **Shared mixture:** every fruiting container inherits all known batch sources.
- **Specific allocation:** select sources separately for each container. Leave unknown allocations empty. A jar may contribute to several containers in that batch.

Mixed culture lines and mixed known strains receive distinct warnings. No “Mixed” catalog strain or hybrid is created. All links are **manual provenance**, not executed spawning. They never mark spawn Used or deduct quantity. A source may appear in manual documentation for more than one batch; this is not a second consumption event. A later spawning module must implement a distinct atomic consumption operation and prevent double consumption there.

On a spore source, **Establish Culture** registers a successfully established independent line. Repeating this action produces distinct CL identities. On a fruiting container, **Establish Tissue Clone** links a successful clone to its actual fruiting source; one known contributing line gives a confirmed parent, multiple give possible parents, and unknown allocation gives unknown ancestry. On a line, **Create Isolate** registers a deliberately selected child with that line as confirmed parent, preserving strain identity. Selection makes no claim of purity or genetic difference. Routine physical-container registration creates no new line. All three actions accept name, date, notes and optional initial physical material; spores/clones can explicitly keep strain unknown.

**Collect Spores** records collection type/date, quantity, notes and physical fruiting source. A mixed-strain source leaves strain unassigned. Derived lines from collected spores retain source-line candidates as **possible**, never automatically confirmed; independent spore cultures are not treated as genetically identical.

Detail panels distinguish genetic parents, possible parents, original spores, tissue/collection sources, grow membership and physical contributions. Related records link in both directions, including archived sources and descendants. Primary strain photo cards remain unchanged. New records reuse existing photo limits, thumbnails, covers, archive/restore and activity logging. Dashboard spawn/fruiting counts now reflect active records, without fabricating monitoring data.

## Fruiting-container strain identification correction

FR properties and listings derive strain identity on every read from their existing physical sources. Shared mixtures use the batch sources; specific allocations use only that individual container's allocated spawn. Acquired fruiting material uses its acquired culture line. Several lines with one common strain display that strain; different known strains display **Mixed Strains** and the contributing names, without implying hybridization. Known and unknown sources display **Partial identification**, including the known names and an explicit unknown-source label. No identifiable strain displays **Unknown**. Known contributing strains link to their catalog records and are also accessible through provenance links. Existing mixed-line and mixed-strain warnings are retained.

The API adds `strain_identification` (`known`, `mixed`, `partial`, `unknown`) and `contributing_strains` (deduplicated ID/name references). Existing `strain_id`/`strain_name` are populated only for a complete single-strain identity; mixed, partial and unknown identities keep those nullable fields empty. Resolution is shared with provenance browsing and includes archived sources. No database migration, backfill, new strain, culture line, or parent relationship is needed; previously registered FR records benefit immediately.

Correction validation: **53 backend tests passed**, **23 frontend tests passed**, and the TypeScript/Vite production build passed. Backend cases cover shared/specific allocations, common strains across distinct lines, mixed/partial/unknown identities, acquired material, and a historical FR record read after restart with all database rows unchanged. One existing upstream Starlette/AnyIO deprecation warning remains.

## Schema and invariants

`0003_lineage` adds `spawn`, `grow_batches`, `batch_sources`, `fruiting_containers`, `fruiting_sources`, `spore_collections`, `line_origins` and `line_parents`. It extends the existing photo/event owner foreign keys and exactly-one-owner check to spawn, batch and fruiting owners, preserving existing rows and IDs. Cover uniqueness is enforced separately for every owner type. `0004_acquisition` adds nullable container/batch supplier metadata.

- `line_origins` is a typed origin record per line: external, spores, clone, isolate or other; spore and fruiting sources have separate constrained foreign keys. Existing 2A lines are backfilled as external with **no parent** or invented origin date, retaining historical acquisition information.
- `line_parents` stores confirmed or possible genetic parent edges. One confirmed parent is permitted; the API requires either one confirmed parent or possible candidates. Self-links are constrained, and recursive SQLite triggers plus API graph checks prevent cycles across either confidence class.
- `batch_sources` links GB batches to SJ/SB spawn, while FR rows carry their batch membership. `fruiting_sources` uses composite foreign keys to ensure each allocation references both a member container and a source of the **same batch**. Composite primary keys prevent duplicate contributions.
- Acquired batches have a line and no fabricated spawn contributions. Prepared batches derive source lines from known spawn; empty/specific unknown allocations remain unknown.
- Permanent ID allocation uses the existing atomic SQLite UPSERT/RETURNING sequence, within `BEGIN IMMEDIATE` transactions. Multi-record registrations roll back together. Archiving never deletes relationships or photo files.
- Ancestry corrections require `expected_revision` and a nonempty reason. Stale edits return 409. History retains previous/corrected relationships and the reason. A clone can only be confirmed against its documented fruiting-source candidates; a selected isolate's recorded parent cannot be silently replaced. Physical contributions are not rewritten by an ancestry correction.

## API

Existing `/api/library` acquisition, CRUD, status, photo and activity routes remain compatible. Generic record kinds now also include `spawn`, `batches`, and `fruiting`. New typed endpoints under `/api/provenance`:

| Method/path | Purpose |
| --- | --- |
| `POST /acquisitions` | Acquire culture, spawn or fruiting material atomically; use existing `/api/library/spores` for spores |
| `POST /grows` | Register prepared GB + FR members and manual source allocations |
| `POST /{lines\|spores\|fruiting}/{id}/establish` | Selected isolate, successful spore culture or tissue clone |
| `POST /fruiting/{id}/collect` | Collect a spore source |
| `GET /{kind}/{id}` | Typed origin, confidence, relationships, warnings and revision |
| `PUT /lines/{id}/ancestry` | Revision-protected genetic parent correction with reason |

Interactive API schemas remain at `/docs`. Names/notes/date are optional. Counts and lists are bounded to 100 containers/sources per registration; library list pagination remains unchanged. Ancestry correction API supports a complete possible-parent set; the compact UI provides exact-parent confirmation or restoration to unknown. Spawn stage editing intentionally exposes Ready/Colonizing; actual consumption is deferred.

## Validation

```bash
cd /workspace/Cultivatinator
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
(cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/alembic current && ../.venv/bin/alembic check)
# Optional tooling: install Playwright in .venv; use installed Chromium.
.venv/bin/python scripts/browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
# Local disposable Docker tests, never production storage:
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t cultivatinator:milestone-2b .
.venv/bin/python scripts/lineage_docker_smoke.py cultivatinator:milestone-2b
```

Proxy CA build secret is needed only for managed TLS proxy environments. TLS verification remains enabled. The browser tests use temporary databases and write screenshots under `/tmp`. The Docker smoke test creates/removes only its uniquely named test container and volume, verifies UID 10001 and port 8085, then recreates the container and verifies retained records, lineage and original photographs. Application runtime requirements and Compose architecture are unchanged. Implementation validation: backend **42 passed** (one upstream Starlette/AnyIO deprecation warning); frontend **17 passed** across 3 files; TypeScript/Vite production build passed; migration upgrade/current/check passed at `0004_acquisition` with no pending schema changes; existing 2A and new 2B desktop/mobile browser smoke tests passed with no browser errors; Docker build and container-recreation smoke passed. Production was not accessed.

## Safe Debian update — manual, after review

Do not run these commands until you choose to deploy the reviewed branch. Keep the current database and photographs intact. Default host port remains 8085; application stays UID/GID 10001:10001 with one worker. The actual production checkout/configuration paths must first be established from the existing deployment, not guessed from the data path.

Inspect the existing deployment locally on the Debian host:

```bash
sudo docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}'
# Set this to the existing Cultivatinator container, not a test container.
container_id=ACTUAL_CONTAINER_ID
sudo docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$container_id"
sudo docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$container_id"
sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$container_id"
```

Record the actual Compose working directory, all config files and overrides, and actual Git checkout separately. Use the same Compose project/options when stopping and starting it. Confirm `/data` maps to `/storage/tv/cultivatinator`; stop and investigate any mismatch. Preserve `.env` and Compose configuration privately, as well as the current Git commit and image tag. Do not display secrets in logs or commit these backups.

A complete **stopped-container** backup is required before any migration:

```bash
set -eu
# Use the actual checkout and Compose directory discovered above.
# Refuse updates over local changes; do not reset or overwrite them.
git -C /actual/git/checkout status --short
old_image=$(sudo docker inspect --format '{{.Image}}' "$container_id")
backup_tag="cultivatinator:pre-2b-$(date +%Y%m%d-%H%M%S)"
sudo docker tag "$old_image" "$backup_tag"
sudo install -d -m 0700 /storage/tv/cultivatinator-backups
backup_file="/storage/tv/cultivatinator-backups/pre-2b-$(date +%Y%m%d-%H%M%S).tar.gz"
sudo docker stop "$container_id"
# Abort on archive or verification failure; keep the service stopped.
sudo tar -C /storage/tv/cultivatinator -czf "$backup_file" .
sudo tar -tzf "$backup_file" >/dev/null
sudo sha256sum "$backup_file"
```

The archive includes database and any WAL/SHM sidecars, **all photos**, files and settings. Copy the verified archive, image tag/commit information and private deployment configuration **off the server**; test restoration on a separate data copy. Keep the old image available (export it if needed). Do not store backups within the live application data directory.

After backup, in the actual Git checkout, fetch and fast-forward the reviewed `feature/milestone-2b-lineage` branch (use `main` only after a separately approved merge). Refuse to proceed if the checkout has changes. In the discovered Compose directory, using its real config files and existing `.env`/project options, run `docker compose up -d --build --wait`, inspect logs, and query `/api/health` using the actual configured host port. Migrations run before requests are accepted. Migration failure is a blocker; preserve data/logs and investigate. This document does not execute deployment.

**Rollback:** stop writes and stop the new container. Preserve the entire post-upgrade data directory separately, then restore the verified pre-upgrade archive into a separate clean directory with UID/GID 10001 ownership. Use the matching pre-upgrade application image and preserved Compose configuration, then point `/data` at that restored copy and verify readiness before resuming use. Never run the old application against the upgraded database or extract over an active/newer database. Downgrade guards refuse to discard 2B lineage or acquisition metadata; a downgrade is not a production rollback procedure. A pre-upgrade backup cannot retain records created after that backup.

## Deferred

Grain/inoculation/agar preparation, routine transfer tracking, failed experiments, germination monitoring, real spawning/consumption transactions and double-consumption prevention, quantity deductions, recipes, fruiting automation, detailed colonization observations, harvest weights/flushes, statistics, hybrid claims, sensors, authentication/multiuser, QR/labels and built-in backup/restore remain deferred. No production deployment or automatic merge is part of 2B.
