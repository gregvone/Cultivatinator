# Cultivatinator

A personal mushroom cultivation and culture lineage application for legally cultivated mushrooms. **Milestone 2E: Dashboard Completion** adds recorded-state attention that stays visible until its cultivation condition is resolved, configurable time reminders, linked cultivation stages, real activity history and recent harvest coverage. See [dashboard rules and Debian review update instructions](docs/MILESTONE_2E.md), [backup and restore](docs/MILESTONE_2D2.md), and [Reports](docs/MILESTONE_2D1.md).

The Industrial Monitoring Console includes a photo-card-first Strain Catalog, acquired culture lines, spore sources, individual physical culture containers, photo galleries, archive/restore, search/filtering, and persistent record activity. The dashboard derives active counts, stage summaries, attention and harvest coverage from recorded facts; environmental monitoring remains deferred. No demonstration records are included. This single-user application has **no general cultivation login**; backup administration defaults to its own passphrase and expiring sessions, with an explicit passwordless Trusted LAN option. It is intended for a trusted private network only. Do not expose it directly to the Internet.

See [Milestone 2C.3 fruiting workflows](docs/MILESTONE_2C3.md) for New Fruiting Container → Mark Pinning → Mark Fruiting → Record Harvest → Next Flush → Finish Grow. A Ready spawn jar/bag is consumed once for all destinations; harvests retain container occupancy until explicit completion/failure. Optional wet/dry weights, subjective potency and environment snapshots preserve individual histories. Pinning, Next Flush, Fruiting, Harvest and Finish Grow forms accept optional photos directly; compact galleries retain exact event/flush ownership and failed uploads can be retried without duplicating the saved event.

See [Milestone 2C.2 cultivation workflows and compatibility](docs/MILESTONE_2C2.md): Inventory is removed from primary navigation; Acquisitions receives outside material and Culture Library owns Add Strain. Recipes has LC Media, Agar, Spawn Seed and Substrate. New LC jars automatically use one designated default media recipe; syringes inherit known source media without a selector. Quick Create saves inoculated material directly, assigns physical labels automatically, and retains separate permanent record IDs. Reusable P/J/L/F labels are released only by explicit lifecycle endings (agar is Used after one successful transfer operation); disposable B/LS/FD labels never repeat. Agar starts Germinating and spawn starts Colonizing; both require an explicit Mark Ready action. Existing records stay unlabeled until Assign Label. No equipment or ingredient prerequisites are required. LC volume tracking stays on culture details; prior preparation/accounting history remains preserved. The Debian checkout, Compose and data coexist at `/storage/tv/cultivatinator`, mounted at `/data`, using port 8085 and UID/GID 10001.

See [Milestone 2C.1 navigation and scope](docs/MILESTONE_2C1.md): use Dashboard Quick Create for material-specific source selection, Acquisitions → Receive Acquisition for outside material, and Culture Library for browsing records and relationships. Spore-print collection remains supported. Preparation and transfers are now operational in 2C.2; actual spawning and harvest tracking are implemented in 2C.3. Legacy acquisition URLs redirect to Acquisitions.

See [Milestone 2B operations and safe upgrade](docs/MILESTONE_2B.md) for universal acquisitions, successful establishments, explicit ancestry, manual grow sources and allocation, spore collection, schema/API details, and backup/rollback precautions. Manual provenance never consumes spawn or marks it Used. Production data is `/storage/tv/cultivatinator`; the current Git/Compose directory is the same host directory, as confirmed for 2C.2. No production update is automatic.

See [Culture Library operations](docs/MILESTONE_2A.md) for registration, photo limits, API details, validation, and historical 2A workflows; use the 2B operations document for current upgrade instructions. Strains are one catalog, with an optional scientific name; there is no required species hierarchy. Receiving spores does not establish a line; the explicit Establish Culture action registers a successful independent establishment. Starting quantities are not live inventory balances.

## Stack and structure

- Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite: `backend/`
- React 19, TypeScript, Vite, Tailwind CSS 4, React Router, Lucide: `frontend/`
- One non-root production container serves the compiled frontend and `/api` on the same origin.
- Existing GPL-3.0 license is preserved in [LICENSE](LICENSE). This software comes without warranty.

## Docker Compose deployment (Debian / Dockge)

For Dockge stack files under `/opt/stacks/cultivatinator` with an existing checkout/data root at `/storage/tv/cultivatinator`, use the [Dockge examples and migration guide](docs/DOCKGE.md). It covers the absolute source build context, Dockge's source mount, existing-container adoption, helper setup and both backup authentication modes.

Requirements: Git, Docker Engine with Compose v2, access to GitHub / npm / PyPI / Docker Hub during build, and a free host port. On the Docker server, run:

```bash
sudo install -d -m 0755 /opt/stacks
sudo git clone https://github.com/gregvone/Cultivatinator.git /opt/stacks/cultivatinator
cd /opt/stacks/cultivatinator
# For the Milestone 2E review implementation:
sudo git switch feature/milestone-2e-dashboard
sudo install -d -o 10001 -g 10001 -m 0750 /storage/tv/cultivatinator
sudo python3 scripts/install_backup_helper.py install --data-root /storage/tv/cultivatinator --compose-file /opt/stacks/cultivatinator/compose.yaml
sudo docker compose up -d --build --wait
sudo docker compose ps
curl --fail http://127.0.0.1:8085/api/health
```

Open `http://SERVER-IP:8085`. Dockge can manage `/opt/stacks/cultivatinator/compose.yaml`. If the stack directory already exists, use the existing checkout rather than cloning over it. The review branch must be available remotely before using these commands. The helper installer requires host Python 3.10+, SQLite/tzdata and systemd; save its private one-time browser setup code. The app receives only a read-only Unix-socket directory, never the Docker socket. For the existing co-located Debian checkout, use the exact [2D.2 setup steps](docs/MILESTONE_2D2.md) instead of cloning a second checkout.

Default host port is **8085**. Copy `.env.example` to `.env` to change `APP_PORT` or `DATA_DIR`. Container port stays 8085. Pre-create the chosen host data directory owned by UID/GID **10001:10001**; the application never starts as root or changes host permissions automatically. For a development Compose deployment, set `DATA_DIR=./data`, create that directory with the same ownership, then use the same Compose command.

On every startup, one application process runs `alembic upgrade head` before accepting requests. Migration failure prevents startup. Do not run multiple instances or workers against the same SQLite directory. Back up before updates, then run `git pull --ff-only` on the intended branch and `docker compose up -d --build --wait`. Automatic downgrade is intentionally avoided.

## Persistent data and recovery

All persistent content is mounted at `/data`:

| Host directory under `/storage/tv/cultivatinator/` | Purpose |
| --- | --- |
| `database/cultivatinator.sqlite3` | SQLite database, including migration version; WAL sidecars may be present |
| `photos/` | Photo originals and generated thumbnails |
| `files/` | Reserved for application-managed files |
| `settings/` | Dashboard reminder preferences |

Container recreation and image replacement preserve persistent data. The existing Debian installation has its Git checkout, Compose file and data together at `/storage/tv/cultivatinator`. **Never replace or archive that entire root as a data-restore operation.** Only `database/`, `photos/`, `files/` and `settings/` belong in a workspace backup; Git, source, Compose and `.env` are excluded.

Use **Settings → Backup & Restore** to establish/unlock the backup administrator and **Create Backup**. In explicitly configured Trusted LAN Mode, allowed clients open this panel immediately without a password. Both server save and browser download are selected by default. Stored backups can be verified, downloaded, restored or explicitly deleted. Automatic weekly backups default to Sunday 03:00 **America/New_York**, keeping the latest **12** successful automatic archives. Manual backups remain until explicitly deleted. Schedule/catalog state lives under `backups/.control/`, outside restored data. The app runs scheduling without a browser and catches up one latest missed occurrence after downtime.

Capture coordinates complete application/photo mutations and uses SQLite's online backup API, including committed WAL contents. ZIP format and migration compatibility are retained. Check browser downloads and keep external copies: same-disk `backups/` cannot protect against total disk failure and is never recursively included in an archive.

Restore from a stored row or **Restore from ZIP**. Both verify/stage first and display date, size, versions and replacement confirmation. A root-owned, Unix-only host helper saves an independent safety ZIP, stops/proves writers stopped, replaces only the four data children, preserves UID/GID 10001, restarts/checks health and reports the authoritative outcome after browser reconnection. Rollback and interrupted recovery retain originals. Git, source, Compose, `.env`, server backups, scheduling and administrator credentials remain in place. Normal operations require no terminal after the one-time helper installation.

See [2D.2 authorization, helper setup, retention, archive limits, safe acceptance and emergency recovery](docs/MILESTONE_2D2.md). HTTP remains suitable only for a trusted network; use HTTPS when protecting credentials from interception is required. Backup sessions are separate from the existing unauthenticated cultivation API. Host CLI tools remain for emergency recovery, and no automatic database downgrade or migration repair occurs.

For your `192.168.68.0/24` installation, merge the two values from [.env.trusted-lan.example](.env.trusted-lan.example) into the existing Debian `.env`, preserving its other settings. Re-run the helper installer, then rebuild/recreate the app as described in [exact mode-switch instructions](docs/MILESTONE_2D2.md#apply-your-debian-configuration-without-changing-cultivation-data). Every allowed LAN client can administer backups/restores. Direct-peer network checks, CSRF and explicit deletion/restore confirmation remain enforced. Forwarded requests are rejected; use a LAN IP or private hostname. The repository's default remains `password`; switching modes preserves credentials and all cultivation data.

## Development without Docker

Requirements: Python 3.12+ and Node **22.12+** (Node 22 LTS recommended), npm. From repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ../backend
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal run `cd frontend && npm run dev`. Vite serves the UI and proxies `/api` to port 8000. Alternatively the production frontend build is served directly by FastAPI at port 8000. Backend commands run from `backend/`; default data is `../data/` and frontend is `../frontend/dist/`. Override with `CULTIVATINATOR_DATA_DIR`, `CULTIVATINATOR_FRONTEND_DIR`, and `CULTIVATINATOR_ENVIRONMENT` as necessary. Cultivation development needs no credentials or external services; Backup & Restore remains locked without its configured host helper. Full browser restore acceptance uses the isolated Docker test installation described in 2D.2. When switching between Docker and native development, use separate data directories to avoid ownership conflicts: for example, export `CULTIVATINATOR_DATA_DIR=/tmp/cultivatinator-native-data` for a disposable native database, or choose a persistent directory owned by your development user. Do not concurrently open the same database from both workflows.

Validation:

```bash
cd backend
../.venv/bin/pytest -q
../.venv/bin/alembic current
../.venv/bin/alembic upgrade head
cd ../frontend
npm test
npm run build
```

`/api/health` verifies connectivity and the current Alembic revision, returning 503 if unhealthy; `/api/dashboard/summary` provides live counts, lifecycle reminders, stages, recorded activity and measured harvest coverage; `/api/app/info` returns safe metadata. Interactive API docs: `/docs`, schema: `/openapi.json`.

## Troubleshooting

- Permission denied at startup: inspect `docker compose logs app`, verify the bind path and UID/GID 10001 ownership; do not use privileged mode or world-writable directories.
- Port occupied: set `APP_PORT` in `.env`, then recreate with `docker compose up -d`.
- API connection error: retry from the displayed error, inspect container logs and `/api/health`. In development, start the backend on port 8000 before Vite.
- Frontend not built: run `npm ci && npm run build` in `frontend/`.
- Failed migration: stop, preserve data and logs, and diagnose the version mismatch. Do not delete the database to bypass an error.
- Docker logs: `docker compose logs --tail=100 app`; readiness: `docker compose ps` and the health endpoint.

See [architecture](docs/ARCHITECTURE.md), [requirements](docs/REQUIREMENTS.md), [roadmap](docs/ROADMAP.md), and [design](docs/DESIGN.md). Deferred modules are documented there. Successful lineage establishment, preparation and inoculation/transfers are implemented. Single-source spawning, substrate snapshots and harvest/flush workflows are implemented in 2C.3. Advanced observations and comparative analytics remain deferred.
