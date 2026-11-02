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

## Milestone 2B: genetic ancestry and physical provenance

`provenance.py` and `provenance_schemas.py` provide typed atomic acquisitions, grow registration, successful establishment, spore collection, related-record browsing and ancestry corrections. `line_origins` keeps spore and fruiting sources in separate constrained relationships; `line_parents` holds confirmed or possible genetic edges with cycle prevention. Acquired 2A lines receive only external/unknown ancestry metadata. `spawn`, `grow_batches`, `batch_sources`, `fruiting_containers`, `fruiting_sources` and `spore_collections` distinguish physical contribution, membership and collection from genetic parentage. Specific allocations use composite foreign keys for same-batch membership. No consumption transaction exists in 2B; later spawning operations must separately own deductions/status changes and prevent duplicate consumption.

Migrations `0003_lineage` and `0004_acquisition` add these structures and nullable acquisition metadata. Existing attachment/activity tables gain three typed owner FKs, extended exactly-one-owner checks and per-owner cover indexes. Archive retains all relationships and content. API ancestry corrections lock writes, check the expected revision, retain old/new parent selections plus a reason, and preserve physical-source links. Detail panels provide source/descendant navigation outside the strain card grid. Dashboard aggregates now count active spawn and fruiting records as well as cultures. No new runtime dependency, service, deployment topology or storage root is introduced. See [2B invariants/API/operations](MILESTONE_2B.md).

## Milestone 2C.1 interface foundation

`quickCreate.ts` centralizes destination/source compatibility and source-context URLs. `QuickCreate.tsx` supplies the dashboard action grid, source-detail disclosure, per-material entry screens and a completed-print form using the existing 2B collection endpoint. Active registration/type filters and explicit Ready spawn are the only availability rules applied; no viability, sterilization or balances are fabricated. Deferred operations expose no write action or acquisition/provenance workaround. `Inventory.tsx` owns outside acquisition/strain management navigation; React Router redirects legacy URLs while preserving search/hash context. The reference catalog retains its data/lineage/photo interfaces. Schema, migrations, backend APIs, Docker port/user/storage and operational semantics are unchanged. See [2C.1 scope](MILESTONE_2C1.md).

## Milestone 2C.2: inventory and operational preparation

`preparation_models.py`, registered in shared Alembic metadata, adds stock, immutable transactions/operations, versioned recipes, immutable batch snapshots, individual prepared materials, pooled reservations, material lifecycle sidecars and exact physical transfers. `preparation.py` owns typed `/api/preparation` endpoints; `material_state.py` projects lifecycle/explicit balances onto legacy records without changing their archive or initial-quantity semantics. `BEGIN IMMEDIATE` serializes stock checks and mutations; Decimal arithmetic with exact text balance/ledger sidecars alongside legacy Numeric(14,3) projections, compatible-dimension unit conversion, request-key replay, revision checks, unique destination transfers and one-time reservation releases protect atomicity. Database guards prevent rewriting committed ledgers, snapshots and transfer history. Migrations `0005_preparation`/`0006_history`/`0007_inventory` are additive and refuse destructive downgrade over new data. No existing stock or readiness is inferred at migration/startup.

Prepared media can own AG/LC/SJ/SB identities before any biological line exists. Physical/spawn rows retain those IDs on inoculation, preserve a routine source's line, and link exact physical origin separately from genetic ancestry. Spore-inoculated agar remains pending until explicit successful establishment binds an independent line. Measured LC depletion blocks reuse; reasoned corrections can restore depleted (not completed/failed) sources. Archive remains separate from operational completion. `preparationApi.ts` uses stable retry keys and integer-thousandth previews; Inventory owns preparation and automatically saves new materials Ready to Inoculate; historical Preparing rows retain their explicit readiness action. Quick Create only inoculates or fills matching ready material. Recipes has its own main navigation workspace and comparison. Actual spawning/FR allocation remains 2C.3. See [2C.2 operations](MILESTONE_2C2.md).

Deployment clarification from the user: repository/Compose and persistent data coexist in `/storage/tv/cultivatinator`, mounted at `/data`. Preserve the arrangement. The current installation has dummy test data and requires no routine backup; when preserving valuable data, back up the whole stopped co-located directory. Root data subdirectories are excluded only from Docker build context, not moved or removed.
