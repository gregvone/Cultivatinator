# Culture Library operations

Milestone 2A adds an empty, database-backed Strain Catalog, acquired culture lines, spore sources, individual physical culture containers, photographs, and record activity. No example records are seeded. Only legally cultivated mushrooms are in scope.

## Using the library

The Culture Library opens on a responsive grid of strain photo cards. Cards show the cover, permanent ID, optional scientific name, status, and totals of all associated lines, spore records, and physical containers (including archived related records). Search matches IDs, names, supplier/source, and descriptive information without case sensitivity. Tabs provide strain, culture-line, spore-source, and physical-container views; status, strain, material, and acquisition-origin filters apply where relevant. Results paginate in groups of 60.

- **Add Strain** creates a catalog entry. Names normalize Unicode, spacing, and case for duplicate detection; duplicates, including archived names, return a conflict. Records are never merged automatically.
- **Receive Culture** guides strain selection (existing, inline creation, or unknown), independent new line or compatible existing line, optional containers, and review. Unrelated supplier batches should normally have separate culture lines. Inline strains and all containers are committed together. Each container has its own immutable ID and detail page; a registration-batch value groups containers registered together. Up to 100 containers can be registered at once.
- **Receive Spores** registers prints, syringes, swabs, or other spore material with a known, inline-created, or unknown strain. It creates no established culture line. Several prints or swabs may be recorded as one source with a registered quantity.
- Descriptive edits never reassign established strain/line relationships. Archive requires confirmation and retains related records and photographs; restore is available on record details. Archived entries are excluded from ordinary selection. There is no permanent record deletion.
- Acquisition dates default to the browser's local date, can be corrected, or cleared for unknown. Quantities may be unknown. **Starting Quantity** / **Registered Quantity** is not a remaining inventory balance. Decimal inputs support three quantity places and two purchase-price places; negative or excessive-precision values are rejected. Purchase prices are descriptive per-container amounts, without cost accounting or currency conversion.
- Every detail page provides photographs and persistent creation, edit, archive/restore, attachment/removal, and cover-selection history. The dashboard counts only active physical cultures. A strain or spore source alone does not increase that count. Other dashboard modules remain unimplemented; their values stay zero, and events are shown on record details rather than the global Recent Activity panel.

## Photos and storage

The existing configurable data directory contains `database/`, `photos/`, `files/`, and `settings/`. In Docker these remain under `/data` on the existing bind mount. Keep the entire mount in backups; the SQLite database alone does not contain photographs.

Attach one or multiple photos after creating any strain, culture line, spore source, or physical container. Uploads are independently committed per file: if a multi-file selection fails partway through, earlier successful files remain visible after refreshing the gallery. JPEG, PNG, and WebP contents are decoded and verified with Pillow regardless of filename or submitted MIME type. Each image must be at most 10 MiB, 24 megapixels, and 12,000 pixels on either side. Generated UUID filenames prevent client paths from influencing storage. Originals are retained; EXIF-oriented WebP thumbnails fit within 640 × 640 pixels. Metadata uses constrained record foreign keys, never binary database blobs. Retrieval only serves known attachments and generated paths.

The first photograph becomes the cover. Users may choose another, open the full original in a keyboard-accessible viewer, or remove an individual photo after confirmation. Removing the cover selects the oldest remaining attachment (timestamp, then ID), or restores the placeholder. Upload failures clean up files and roll back metadata. Removal stages files on the same filesystem and restores them on a failed database transaction. Filesystem and SQLite transactions cannot be atomic across sudden power loss: after an interrupted storage operation, preserve the complete data directory before investigating hidden `.removed` staging files or unattached originals. Do not blindly delete files during startup or upgrades.

The container still runs as UID/GID 10001:10001. The existing host data mount must be writable by that user. Application upgrades do not change ownership, clear storage, or overwrite existing photos. Do not run multiple workers/instances on the same SQLite data directory.

## API and database

Interactive typed API documentation remains at `/docs`. Library endpoints live under `/api/library`:

- `GET /{strains|lines|spores|physical}` supports `q`, `status=active|archived|all`, relationship/type/origin filters, `limit` (1–1000), and `offset`.
- `POST /strains`, `POST /spores`, and transactional `POST /receive-culture` register records.
- `GET /{kind}/{id}`, `PATCH /{kind}/{id}`, `POST /{kind}/{id}/status`, and `GET /{kind}/{id}/activity` manage existing records.
- `POST /{kind}/{id}/photos` accepts one multipart `file`; `GET` on the same path lists attachments. `GET /photos/{uuid}/{original|thumbnail}`, `POST /photos/{uuid}/cover`, and `DELETE /photos/{uuid}` manage photos.

Migration `0002_culture_library` follows `0001_foundation`. The tables are `strains`, `culture_lines`, `spore_sources`, `physical_cultures`, `identity_sequences`, `photo_attachments`, and `activity_events`. Foreign keys do not cascade-delete history. Sequences use SQLite UPSERT/RETURNING under a `BEGIN IMMEDIATE` write transaction; there is no unprotected max-ID calculation. Prefixes: STR (strain), CL (line), SP (spores), LC (liquid-culture jar or syringe), AG (agar plate), SL (slant), PC (other physical culture). IDs never change when names or material descriptions change. Archive does not release sequence numbers.

## Validation

From the repository root:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
(cd backend && ../.venv/bin/alembic upgrade head && ../.venv/bin/alembic current && ../.venv/bin/alembic check)
```

Backend tests use isolated temporary databases; they cover both a fresh database and upgrading a Milestone 1 baseline, concurrency, rollback, photo content validation, archive/restore, quantities, and restart persistence. Foundation schema assertions now expect the added tables and migration head.

An optional browser smoke test creates its own disposable local backend and database and uses the compiled frontend. With Playwright and Pillow available in the invoking Python environment, run `python scripts/browser_smoke.py /usr/bin/chromium`. It exercises actual registrations, uploads, cover selection, photo viewer, physical editing, dashboard counts, and desktop/mobile navigation. Screenshots are written to `/tmp`, outside the checkout. This is optional development tooling, not a runtime dependency.

Docker/Compose can be tested on a separate project name, loopback port, and separate UID-10001-owned data mount. Never use production data for tests. Behind a managed TLS proxy, build with `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t cultivatinator:local .`; ordinary deployments continue using `docker compose up -d --build --wait`.

## Updating the existing Debian installation

Do this only when you choose to deploy the reviewed branch. These commands update the existing checkout and back up the actual `/data` bind mount, including custom paths from `.env`. Keep the archive off-server as well. No database reset or automatic downgrade is used. Migrations run at application startup; if startup fails, preserve storage and logs and investigate. Restoring an earlier application version may require restoring its matching stopped-data backup, not downgrading a live database.

```bash
set -e
cd /opt/stacks/cultivatinator
# Refuse to proceed over tracked local changes.
sudo git diff --exit-code
sudo git diff --cached --exit-code
container_id=$(sudo docker compose ps -q app)
test -n "$container_id"
data_path=$(sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$container_id")
test -n "$data_path" && test "$data_path" != /
sudo test -d "$data_path"
backup_path="/opt/stacks/cultivatinator-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
sudo docker compose stop app
# If backup or verification fails, stop here; the old app remains stopped.
sudo tar -C "$data_path" -czf "$backup_path" .
sudo tar -tzf "$backup_path" >/dev/null
printf 'Verified backup: %s\n' "$backup_path"
sudo git fetch origin
sudo git switch feature/milestone-2a-culture-library
sudo git pull --ff-only origin feature/milestone-2a-culture-library
sudo docker compose up -d --build --wait
sudo docker compose ps
sudo docker compose exec -T app python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8085/api/health", timeout=10).read().decode())'
sudo docker compose logs --tail=100 app
```

The feature branch is for review; after merging, use `main` for the switch/pull steps instead. Default host port stays 8085; `.env` overrides remain supported. No commands above remove the database or persistent directories, and the running application remains non-root. No production deployment is performed by the implementation task.

## Next: Milestone 2B

Culture ancestry and lineage relationships remain deferred. A spore source may later be an ancestor of multiple independently established culture lines, each with its own identity. Cloning, isolates, germination, propagation/transfer operations, lineage visualization, and inventory consumption are not implemented in 2A. Do not infer ancestry from names, shared suppliers, or matching strain IDs.
