# Cultivatinator

A personal mushroom cultivation, culture lineage, and inventory management application for legally cultivated mushrooms. **Milestone 2C.1: Dashboard Quick Create & Culture Library Redesign** builds on the completed lineage and provenance foundation.

The Industrial Monitoring Console includes a photo-card-first Strain Catalog, acquired culture lines, spore sources, individual physical culture containers, photo galleries, archive/restore, search/filtering, and persistent record activity. The dashboard counts active registered physical cultures; spawn and fruiting counts reflect active registered records; monitoring and unimplemented modules remain empty. No demonstration records or login are included. This single-user application has **no authentication** and is intended for a trusted private network only. Do not expose it directly to the Internet.

See [Milestone 2C.1 navigation and scope](docs/MILESTONE_2C1.md): use Dashboard Quick Create for material-specific source selection, Inventory → Receive Acquisition for outside material, and Culture Library for browsing records and relationships. Spore-print collection uses the existing working operation; preparation, transfers, inoculation and actual spawning are clearly deferred without creating records. Legacy acquisition URLs redirect to Inventory.

See [Milestone 2B operations and safe upgrade](docs/MILESTONE_2B.md) for universal acquisitions, successful establishments, explicit ancestry, manual grow sources and allocation, spore collection, schema/API details, and backup/rollback precautions. Manual provenance never consumes spawn or marks it Used. Production data is `/storage/tv/cultivatinator`; discover the actual Git and Compose directories separately. No production update is automatic.

See [Culture Library operations](docs/MILESTONE_2A.md) for registration, photo limits, API details, validation, and historical 2A workflows; use the 2B operations document for current upgrade instructions. Strains are one catalog, with an optional scientific name; there is no required species hierarchy. Receiving spores does not establish a line; the explicit Establish Culture action registers a successful independent establishment. Starting quantities are not live inventory balances.

## Stack and structure

- Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, SQLite: `backend/`
- React 19, TypeScript, Vite, Tailwind CSS 4, React Router, Lucide: `frontend/`
- One non-root production container serves the compiled frontend and `/api` on the same origin.
- Existing GPL-3.0 license is preserved in [LICENSE](LICENSE). This software comes without warranty.

## Docker Compose deployment (Debian / Dockge)

Requirements: Git, Docker Engine with Compose v2, access to GitHub / npm / PyPI / Docker Hub during build, and a free host port. On the Docker server, run:

```bash
sudo install -d -m 0755 /opt/stacks
sudo git clone https://github.com/gregvone/Cultivatinator.git /opt/stacks/cultivatinator
cd /opt/stacks/cultivatinator
# For the Milestone 2C.1 review implementation:
sudo git switch feature/milestone-2c1-quick-create
sudo install -d -o 10001 -g 10001 -m 0750 /storage/tv/cultivatinator
sudo docker compose up -d --build --wait
sudo docker compose ps
curl --fail http://127.0.0.1:8085/api/health
```

Open `http://SERVER-IP:8085`. Dockge can manage `/opt/stacks/cultivatinator/compose.yaml`. If the stack directory already exists, use the existing checkout rather than cloning over it. The review branch must be available remotely before using these commands.

Default host port is **8085**. Copy `.env.example` to `.env` to change `APP_PORT` or `DATA_DIR`. Container port stays 8085. Pre-create the chosen host data directory owned by UID/GID **10001:10001**; the application never starts as root or changes host permissions automatically. For a development Compose deployment, set `DATA_DIR=./data`, create that directory with the same ownership, then use the same Compose command.

On every startup, one application process runs `alembic upgrade head` before accepting requests. Migration failure prevents startup. Do not run multiple instances or workers against the same SQLite directory. Back up before updates, then run `git pull --ff-only` on the intended branch and `docker compose up -d --build --wait`. Automatic downgrade is intentionally avoided.

## Persistent data and recovery

All persistent content is mounted at `/data`:

| Host directory under `/storage/tv/cultivatinator/` | Purpose |
| --- | --- |
| `database/cultivatinator.sqlite3` | SQLite database, including migration version; WAL sidecars may be present |
| `photos/` | Photo originals and generated thumbnails |
| `files/` | Reserved for application-managed files |
| `settings/` | Reserved for future persistent settings |

Container recreation and image replacement preserve the bind-mounted directory. Do not remove it when updating. UI backup/restore is **not implemented**. For a consistent Docker-level backup, stop writes by stopping the container and archive the entire directory (including SQLite sidecars):

```bash
cd /opt/stacks/cultivatinator
sudo docker compose stop app
sudo tar -C /storage/tv -czf /opt/stacks/cultivatinator-backup-$(date +%Y%m%d-%H%M%S).tar.gz cultivatinator
sudo docker compose start app
```

Check the tar command succeeded before relying on the archive; keep a copy off the server. To restore: stop the service, preserve the current data directory separately, inspect a trusted archive, extract its `cultivatinator/` directory under `/storage/tv`, restore UID/GID 10001 ownership, and start the **matching application version**. Test recovery on a separate copy first. No live-file copying procedure is promised safe.

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

In another terminal run `cd frontend && npm run dev`. Vite serves the UI and proxies `/api` to port 8000. Alternatively the production frontend build is served directly by FastAPI at port 8000. Backend commands run from `backend/`; default data is `../data/` and frontend is `../frontend/dist/`. Override with `CULTIVATINATOR_DATA_DIR`, `CULTIVATINATOR_FRONTEND_DIR`, and `CULTIVATINATOR_ENVIRONMENT` as necessary. No credentials or external services are required. When switching between Docker and native development, use separate data directories to avoid ownership conflicts: for example, export `CULTIVATINATOR_DATA_DIR=/tmp/cultivatinator-native-data` for a disposable native database, or choose a persistent directory owned by your development user. Do not concurrently open the same database from both workflows.

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

`/api/health` verifies connectivity and the current Alembic revision, returning 503 if unhealthy; `/api/dashboard/summary` counts active physical cultures and keeps unimplemented metrics zero; `/api/app/info` returns safe metadata. Interactive API docs: `/docs`, schema: `/openapi.json`.

## Troubleshooting

- Permission denied at startup: inspect `docker compose logs app`, verify the bind path and UID/GID 10001 ownership; do not use privileged mode or world-writable directories.
- Port occupied: set `APP_PORT` in `.env`, then recreate with `docker compose up -d`.
- API connection error: retry from the displayed error, inspect container logs and `/api/health`. In development, start the backend on port 8000 before Vite.
- Frontend not built: run `npm ci && npm run build` in `frontend/`.
- Failed migration: stop, preserve data and logs, and diagnose the version mismatch. Do not delete the database to bypass an error.
- Docker logs: `docker compose logs --tail=100 app`; readiness: `docker compose ps` and the health endpoint.

See [architecture](docs/ARCHITECTURE.md), [requirements](docs/REQUIREMENTS.md), [roadmap](docs/ROADMAP.md), and [design](docs/DESIGN.md). Deferred modules are documented there. Successful lineage establishment and basic grow provenance are implemented; preparation, consumption and harvest workflows remain deferred.
