# Architecture

## Runtime and project organization

Python 3.12 and FastAPI provide a small typed HTTP API. SQLAlchemy 2 owns connections; Alembic owns migrations. SQLite fits a private single-user deployment without additional infrastructure. React / TypeScript uses Vite, Tailwind CSS, React Router, and Lucide without a UI framework or global state library.

`backend/app/config.py` holds environment-derived configuration. `database.py` owns engine creation, connection PRAGMAs, migration configuration, and a session lifecycle helper for future operations. `api/routes.py` owns foundation HTTP endpoints; `schemas.py` defines Pydantic response contracts. `main.py` owns application lifetime, safe error handling, and production SPA serving. `frontend/src/api.ts` and `useApi.ts` isolate request and cancellation behavior from reusable UI, shell, and page components.

## API and errors

- GET `/api/health`: status, database connectivity, and migration revision. HTTP 200 when healthy, 503 otherwise.
- GET `/api/dashboard/summary`: nonnegative counts plus typed empty attention, cultivation, activity, and environmental lists. Counts deliberately return zero until real aggregate queries exist; no fake database records.
- GET `/api/app/info`: name, version, environment label, storage description; no paths or secrets.
- `/docs`, `/redoc`, `/openapi.json`: FastAPI documentation.

Validation uses Pydantic; future inputs must have explicit schemas and constraints. Expected HTTP errors use `detail`; unexpected failures return a generic detail while tracebacks stay in server logs. The UI handles loading, network/HTTP failure, retry, and request cancellation. Unknown API and asset paths return 404 rather than the SPA document. Browser routes fall back to the SPA.

## Database lifecycle and migrations

One Uvicorn worker initializes storage, runs Alembic to head, then serves traffic. A failed migration stops startup. Engine disposal is guaranteed on shutdown, SQLite connections use foreign-key enforcement and a 30-second busy timeout, and initialization enables WAL. Future per-request sessions must close after use, and writes must use explicit transaction scopes.

Migration `0001_foundation` is the baseline. Incremental migration `0002_culture_library` adds the seven Culture Library tables; Alembic maintains `alembic_version`. All future schema evolution uses reviewed migrations; no runtime `create_all`. Run Alembic from `backend/` with the same `CULTIVATINATOR_DATA_DIR` as the application. Back up before schema changes. SQLite migrations may need Alembic batch mode for table changes.

## Deployment and storage

The Dockerfile builds frontend assets and a Python virtualenv in separate stages, then serves both through one non-root UID/GID 10001 application container on internal port 8085. Compose defaults host port 8085 and restart unless stopped. No privileges, no added services. Health checks query the database and migration revision through HTTP. Logs go to stdout/stderr.

`/data/database`, `/data/photos`, `/data/files`, and `/data/settings` are inside one host bind mount; only the database currently contains application data. Host directories must be writable by UID/GID 10001. Live processes are disposable. A future complete backup must include the database, photographs, files, and persistent settings together. Current recovery uses a stopped-container whole-directory archive as described in README. No built-in backup or restore exists yet.

## Rules for future schemas

- Keep a single strain catalog with optional scientific-name reference; separate biological identity (strain classification and acquired culture lines) from physical material (plates, LC containers, spore samples, spawn, fruiting units).
- Keep physical transfer/propagation history distinguishable from genetic ancestry (spore-derived lines, clones, isolates, experimental parent relationships).
- Give every physical record a permanent unique identifier. Optional custom names never replace identifiers.
- Operations must support multiple source records; batches must support individual child records.
- Inventory additions, usage, corrections, and disposal form traceable transactions. Deductions and associated operations must be atomic; failures leave no partial changes.
- Support partial consumption and precise quantities with decimal/fixed-point accounting, avoiding floating-point inventory arithmetic.
- Archive historical records by default rather than deleting them; keep corrections traceable.
- Model observations, transfers, milestones, and harvests as activity events; preserve photo associations with individual records/events and include photographs in complete backups.

These constraints also guide future modules; only the Culture Library subset is implemented. No authentication is implemented; private-network access is required.

## Culture Library implementation (2A)

`models.py` defines Strain → CultureLine → PhysicalCulture and the separate Strain → SporeSource association. Strain is optional for acquired lines/spores; a spore registration never creates a culture line. Archive flags preserve all foreign keys. PhotoAttachment and ActivityEvent each require exactly one of four real owner foreign keys, enforced by a check constraint. Record history has no user/account dependency. See [operations](MILESTONE_2A.md) for identifiers, API paths, storage limits and update commands.

`library.py` owns typed registration, lookup, editing, status, search, and history endpoints with Pydantic input contracts in `library_schemas.py`. Writable operations lock SQLite with BEGIN IMMEDIATE before decisions; sequence UPSERT/RETURNING, inline strains, lines, every batch child, and events commit together. Quantities use Numeric(14,3), prices Numeric(14,2); Pydantic rejects non-finite, negative, over-precision and unsupported-unit inputs. No live inventory accounting exists.

`photos.py` verifies actual decoded JPEG/PNG/WebP contents with Pillow, retains UUID-named originals and 640px WebP thumbnails under configured photos storage, and returns opaque attachment URLs. Exclusive writes and transaction failure cleanup protect upload integrity. Removal stages files before metadata changes, restores them on rollback, and selects a deterministic remaining cover. A partial unique index enforces one cover per owner. A power loss between filesystem and database operations still requires offline inspection; there is no claim of cross-system crash atomicity.

The React library uses a photo-card grid, shared shell, typed API client, guided registration/review, descriptive edit forms, related record links, photo galleries and a modal original-image viewer. It keeps no persistent domain state in browser storage. The dashboard queries active PhysicalCulture rows only; per-record activity is separate from the still-empty global activity panel. No new services, authentication, or deployment infrastructure are introduced.
