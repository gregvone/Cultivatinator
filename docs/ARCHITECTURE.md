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

`/data/database`, `/data/photos`, `/data/files`, and `/data/settings` are inside one host bind mount. Host directories must be writable by UID/GID 10001. Live processes are disposable. Settings provides a complete ZIP download; the standard-library host restore utility replaces only these four data children, preserving the co-located Git checkout, source and Compose configuration. See the 2D.2 architecture below and [maintenance instructions](MILESTONE_2D2.md).

## Rules for future schemas

- Keep a single strain catalog with optional scientific-name reference; separate biological identity (strain classification and acquired culture lines) from physical material (plates, LC containers, spore samples, spawn, fruiting units).
- Keep physical transfer/propagation history distinguishable from genetic ancestry (spore-derived lines, clones, isolates, experimental parent relationships).
- Give every physical record a permanent unique identifier. Optional custom names never replace identifiers.
- Operations must support multiple source records; batches must support individual child records.
- Inventory additions, usage, corrections, and disposal form traceable transactions. Deductions and associated operations must be atomic; failures leave no partial changes.
- Support partial consumption and precise quantities with decimal/fixed-point accounting, avoiding floating-point inventory arithmetic.
- Archive historical records by default rather than deleting them; keep corrections traceable.
- Model observations, transfers, milestones, and harvests as activity events; preserve photo associations with individual records/events and include photographs in complete backups.

These constraints also guide future modules and the implemented cultivation/harvest workflows. The cultivation API has no general authentication; private-network access is required. 2D.2 separately authorizes backup administration.

## Culture Library implementation (2A)

`models.py` defines Strain → CultureLine → PhysicalCulture and the separate Strain → SporeSource association. Strain is optional for acquired lines/spores; a spore registration never creates a culture line. Archive flags preserve all foreign keys. PhotoAttachment and ActivityEvent each require exactly one of four real owner foreign keys, enforced by a check constraint. Record history has no user/account dependency. See [operations](MILESTONE_2A.md) for identifiers, API paths, storage limits and update commands.

`library.py` owns typed registration, lookup, editing, status, search, and history endpoints with Pydantic input contracts in `library_schemas.py`. Writable operations lock SQLite with BEGIN IMMEDIATE before decisions; sequence UPSERT/RETURNING, inline strains, lines, every batch child, and events commit together. Quantities use Numeric(14,3), prices Numeric(14,2); Pydantic rejects non-finite, negative, over-precision and unsupported-unit inputs. No live inventory accounting exists.

`photos.py` verifies actual decoded JPEG/PNG/WebP contents with Pillow, retains UUID-named originals and 640px WebP thumbnails under configured photos storage, and returns opaque attachment URLs. Exclusive writes and transaction failure cleanup protect upload integrity. Removal stages files before metadata changes, restores them on rollback, and selects a deterministic remaining cover. A partial unique index enforces one cover per owner. A power loss between filesystem and database operations still requires offline inspection; there is no claim of cross-system crash atomicity.

The React library uses a photo-card grid, shared shell, typed API client, guided registration/review, descriptive edit forms, related record links, photo galleries and a modal original-image viewer. It keeps no persistent domain state in browser storage. The dashboard queries active PhysicalCulture rows only; per-record activity is separate from the still-empty global activity panel. No new services, authentication, or deployment infrastructure are introduced.

## Milestone 2B: genetic ancestry and physical provenance

`provenance.py` and `provenance_schemas.py` provide typed atomic acquisitions, grow registration, successful establishment, spore collection, related-record browsing and ancestry corrections. `line_origins` keeps spore and fruiting sources in separate constrained relationships; `line_parents` holds confirmed or possible genetic edges with cycle prevention. Acquired 2A lines receive only external/unknown ancestry metadata. `spawn`, `grow_batches`, `batch_sources`, `fruiting_containers`, `fruiting_sources` and `spore_collections` distinguish physical contribution, membership and collection from genetic parentage. Specific allocations use composite foreign keys for same-batch membership. No consumption transaction exists in 2B; later spawning operations must separately own deductions/status changes and prevent duplicate consumption.

Migrations `0003_lineage` and `0004_acquisition` add these structures and nullable acquisition metadata. Existing attachment/activity tables gain three typed owner FKs, extended exactly-one-owner checks and per-owner cover indexes. Archive retains all relationships and content. API ancestry corrections lock writes, check the expected revision, retain old/new parent selections plus a reason, and preserve physical-source links. Detail panels provide source/descendant navigation outside the strain card grid. Dashboard aggregates now count active spawn and fruiting records as well as cultures. No new runtime dependency, service, deployment topology or storage root is introduced. See [2B invariants/API/operations](MILESTONE_2B.md).

## Milestone 2C.1 interface foundation

`quickCreate.ts` centralizes destination/source compatibility and source-context URLs. `QuickCreate.tsx` supplies the dashboard action grid, source-detail disclosure, per-material entry screens and a completed-print form using the existing 2B collection endpoint. Active registration/type filters and explicit Ready spawn are the only availability rules applied; no viability, sterilization or balances are fabricated. Deferred operations expose no write action or acquisition/provenance workaround. The former Inventory navigation has been replaced by `Acquisitions.tsx` and Culture Library strain management; React Router redirects legacy URLs while preserving search/hash context. The reference catalog retains its data/lineage/photo interfaces. Schema, migrations, backend APIs, Docker port/user/storage and operational semantics are unchanged. See [2C.1 scope](MILESTONE_2C1.md).

## Milestone 2C.2: inventory and operational preparation

`preparation_models.py`, registered in shared Alembic metadata, adds stock, immutable transactions/operations, versioned recipes, immutable batch snapshots, individual prepared materials, pooled reservations, material lifecycle sidecars and exact physical transfers. `preparation.py` owns typed `/api/preparation` endpoints; `material_state.py` projects lifecycle/explicit balances onto legacy records without changing their archive or initial-quantity semantics. `BEGIN IMMEDIATE` serializes stock checks and mutations; Decimal arithmetic with exact text balance/ledger sidecars alongside legacy Numeric(14,3) projections, compatible-dimension unit conversion, request-key replay, revision checks, unique destination transfers and one-time reservation releases protect atomicity. Database guards prevent rewriting committed ledgers, snapshots and transfer history. Migrations `0005_preparation`/`0006_history`/`0007_inventory` are additive and refuse destructive downgrade over new data. No existing stock or readiness is inferred at migration/startup.

Prepared media can own AG/LC/SJ/SB identities before any biological line exists. Physical/spawn rows retain those IDs on inoculation, preserve a routine source's line, and link exact physical origin separately from genetic ancestry. Spore-inoculated agar remains pending until explicit successful establishment binds an independent line. Measured LC depletion blocks reuse; reasoned corrections can restore depleted (not completed/failed) sources. Archive remains separate from operational completion. `preparationApi.ts` uses stable retry keys and integer-thousandth previews; Historical preparation remains available with explicit legacy readiness and completion paths. Normal Quick Create saves inoculated records directly without stock or reservations, as described below. Recipes has dedicated category/list/detail routes and comparison. Actual spawning/FR allocation remains 2C.3. See [2C.2 operations](MILESTONE_2C2.md).

Deployment clarification from the user: repository/Compose and persistent data coexist in `/storage/tv/cultivatinator`, mounted at `/data`. Preserve the arrangement. Only `database/`, `photos/`, `files/` and `settings/` are persistent application data. Do not archive or replace the whole co-located directory during backup/restore. Root data subdirectories are excluded from Docker build context; 2D.2 adds a complete data-only backup and safe restore.


### Final 2C.2 workflow redesign

`POST /api/preparation/create` atomically snapshots a selected recipe, allocates individual destination IDs and records inoculation/physical provenance without container reservations or ingredient deductions. It reuses batch/material/transfer tables and source accounting; successful direct operations commit as inoculated. Routine transfers preserve genetic lines; spores retain pending independent establishment. Known LC requires measured use; unknown balances are never inferred. Recipe ingredient definitions can be named independently of inventory, while legacy inventory preparation still validates actual stock links. Recipe deletion checks snapshot dependencies inside the serialized transaction; used recipes are archived instead. Mutation request keys, immutable history and prior retry fingerprints remain compatible.

`0008_recipes` adds a nullable recipe edit timestamp without backfilling or changing prior migrations/data. Dedicated category/list/detail/editor routes replace the former recipe screen. `DirectCreate.tsx`, `Recipes.tsx`, `Growing.tsx` and `LegacyInoculation.tsx` implement direct creation, four-category recipe management, production lists and previous-prepared completion respectively. The Inventory workspace is removed; its historical accounting APIs and data remain compatible. `/growing` projects source/date/recipe information onto legacy and new biological records, including pending spore establishments.


### Final 2C.2 simplification

`0009_lc_default` adds a singleton FK to an explicitly designated active LC recipe; historical definitions are never auto-selected or rewritten. Serialized default designation/edit/archive safeguards keep one active default and protect deletion. `/create` resolves the default for LC jars, but derives media snapshots from the actual source for syringes, including older revisions/archived definitions. Syringes store transfer provenance with no new processing/ingredients/preparation date. Ledger accounting remains independent of media choice and historical request-key replay remains stable.

Main navigation replaces Inventory with Acquisitions and moves Add Strain to Culture Library. Four recipe categories separate LC Media and grain Spawn Seed. LC forms have no recipe selector. Removed Inventory/new-preparation page wrappers are not mounted; old URLs redirect with context to Acquisitions, Culture Library or historical material routes. Historical tables, APIs, reservations, snapshots and readiness completion remain compatible, while normal creation requires no stock. LC volume correction remains directly on the culture detail page.

## Milestone 2C.3: operational fruiting

See [2C.3](MILESTONE_2C3.md) for lifecycle/API rules. `fruiting.py` uses the existing immediate transaction/idempotency journal and label allocator, with typed models in `fruiting_models.py`. Migration 0011 adds seven tables without rewriting prior tables or backfilling legacy events. Each new operational FR has one immutable permanent spawn source and snapshots. Native FR stage values remain compatible; `fruiting_stage`/`current_flush` project the operational state. Explicit legacy terminal writes synchronize run endings.

Harvest weights are nullable Decimal grams; measured-entry counts accompany sums. Full immutable harvest revisions retain edits. Harvest photos reuse the existing upload/cover/viewer/removal implementation with an additional typed harvest link committed atomically. Configuration is a revision-checked singleton; immutable per-grow environment snapshots and append-only meaningful changes support future comparison without daily logs. The frontend reuses shared fields, label choices, photo gallery and command handling; stable retries remain valid after a source was consumed.

### 2C.3 event-photo enhancement

Migration 0012 adds Pinning notes and typed FR/flush photo relationships without rewriting 0011 or old data. Pinning and harvest uploads share `photos.store_upload`, validation, files, thumbnails and existing cover/removal logic. `PhotoUploads.tsx` tracks individual pending files; inline forms retain the saved event response while retrying only remaining photos. Gallery refreshes are scoped and nonblocking so a failed read cannot discard the retry queue. Pinning targets use the returned flush number, never the current display label or a default flush. Compact galleries show photos directly in each event's history.


Migration 0013 extends that workflow to Fruiting and Finish Grow. It adds nullable per-flush Fruiting notes and `journal_photos` links constrained to a recorded Fruiting flush or the grow's recorded completion. Photos remain ordinary FR-owned attachments with event metadata; the existing storage/validation/viewer/removal implementation is reused. Prior migrations, photographs and events are preserved. Inline completion retains its saved response and retry queue through terminal-status refreshes so a failed file never repeats completion or reusable-label release. The timeline displays Pinning, Fruiting and individual Harvest galleries per flush, then Grow Completed with its own date, notes and gallery.


## Milestone 2C.4: shared UI disclosure

`CollapsiblePanel.tsx` supplies independent native details/summary sections with mounted children, nonpersistent expansion state, accessible controls and automatic validation disclosure. `RecordHeader.tsx` standardizes identity/status/dates; `RecordNextAction.tsx` derives existing workflow links from the existing eligibility helper. Fruiting history groups flushes without changing their ordering or photo URLs; compact gallery controls retain upload state while hidden. Record navigation resets panel defaults, whereas refreshes and collapses retain forms/retry queues. Shared CSS standardizes primary, secondary and terminal controls. No backend or database changes are involved. See [2C.4 operations and scope](MILESTONE_2C4.md).


## Milestone 2D.1: read-only performance reporting

`reports.py` exposes GET `/api/reports/performance` with typed Pydantic contracts in `report_schemas.py`. Four set/aggregate SELECTs resolve per-FR measurements, recorded dates, labels and shared/specific/acquired sources under a consistent read transaction. Integer milligram sums and Decimal per-container averages avoid harvest-count weighting and missing-as-zero errors. Genetics use actual source line/strain IDs; recipe grouping uses immutable run snapshots/revisions, never editable recipe contents. No schema, historical record or cultivation mutation changes are required.

`Reports.tsx`, `reportApi.ts` and `PerformanceBars.tsx` use existing navigation/UI/error handling, CSS horizontal bars and accessible expandable tables. Unknown/mixed identities remain unranked; measured samples/source counts, incomplete exclusions, separate current active scope, date bounds and terminal failure denominators are explicit. See [2D.1 calculation and population rules](MILESTONE_2D1.md).


## Milestone 2D.2: coordinated backup and stopped-data restore

`backups.py` installs a pure-ASGI asynchronous mutation gate around the full lifetime of every mutating request, covering photo upload before commit and photo-removal rollback/cleanup after transactions. Backup capture uses the same gate, a SQLite writer reservation and a separate read-only online-backup connection. It inventories only the four persistent directories, snapshots committed WAL data, verifies integrity/foreign keys/schema/photo references, and writes a ZIP with SHA-256 inventory. Reads remain available; writes resume before archive transmission. Existing mutation APIs and domain data remain compatible.

`backup_format.py` is standard-library-only and shared by the backend and host CLI. It bounds the ZIP central directory before parsing, validates format/version/migration and every path/member/checksum, and extracts exclusively into private staging. `backup_schema.json` is the trusted schema contract for current migration `0013_journal_photos`, including constraints, indexes and immutable-history triggers. Reflection-dependent constraint ordering is normalized. No schema migration or domain model change is introduced. `version.py` exposes the same existing application version without importing runtime dependencies into the CLI.

`POST /api/backups/prepare` stages a verified archive and returns an opaque single-use URL with a five-minute TTL. GET streams a native browser download; DELETE cancels an unused ticket. Direct GET `/api/backups/download` supports the host safety-copy workflow. Artifact cleanup covers capture failure/cancellation, stream failures, expiration, shutdown and stale files at next startup. The frontend uses an abortable preparation request and native download manager, avoiding a second archive-sized JavaScript buffer. Busy/error/retry and external-copy wording use existing Settings panels and controls.

`scripts/workspace_backup.py` and `restore_workspace.py` implement host verification, explicit confirmed restore and interrupted recovery with no pip dependencies. They validate incoming data before shutdown, retain an independently verified pre-restore ZIP plus original directories, use the existing local Compose service, check stopped process state/host file descriptors/exclusive SQLite access, and replace only four child directories by same-filesystem renames. Restored files are owned by 10001:10001. An fsynced operation journal, retained originals and a root interruption marker support automatic rollback and recovery after abrupt termination. Health checks verify connectivity, migration head and application version. The tool starts an existing container and never builds, recreates, deploys or changes source/configuration.

Application lifetime holds an OS file lease outside the backed-up data, enforcing one process per root. An incomplete restore marker prevents initialization/migration before missing or mixed directories can be opened. Restore uses a separate operation lock and obtains the runtime lease only after shutdown. This supplements, rather than replaces, the single-worker rule. The 2D.2 revision adds authorized browser management, in-process weekly scheduling and a restricted Unix-only host helper, described below. The original host CLI remains for emergency recovery. Archive checksums provide integrity, not authenticity or encryption. See [2D.2 limits, disk requirements, exact Debian commands and recovery](MILESTONE_2D2.md).


### 2D.2 revision: browser administration, storage and host helper

`backup_store.py` owns only generated UUID archives/receipts and durable schedule state under `backups/.control/`, excluded from Git, Docker context and every archive. A verified hidden partial is published exclusively with durable receipt bookkeeping; interrupted publication is reconciled at startup. Manual archives are never automatically deleted. `backup_manager.py` serializes jobs, uses the existing mutation gate/snapshot mechanism, and runs the weekly timer in the single app process. `backup_schedule.py` resolves IANA wall-clock weekly occurrences across DST (first fall occurrence; spring gap advances to the first valid minute). UTC occurrence receipts prevent duplicate success across crashes; one latest missed run is caught up and failures retry after 15 minutes. Retention prunes only after new verified automatic success; restore locks protect archive usage.

`backup_access.py` and `backup_management.py` add focused administrator setup/unlock, HttpOnly scoped sessions, CSRF/origin checks, destinations, catalog/verify/download/delete, schedule editing and staged restore APIs. Both destinations share a single captured ZIP. Uploads are streamed with limits into reserved temporary staging; they never auto-restore or silently become manual archives. Existing backup API shapes remain available behind the required authorization. `BackupRestore.tsx` uses existing panels/controls, displays schedule/storage/rows, separate deletion and restore confirmation, native downloads and honest reconnection status during downtime.

The host systemd helper (`maintenance_service.py`) owns credentials, sessions, previews and persisted operation state under root-private `/var/lib/cultivatinator-maintenance`. The installer copies standard-library code/schema/revisions and emergency CLI into root-owned `/opt/cultivatinator-maintenance`, freezes resolved Compose in root-owned `/etc/cultivatinator-maintenance`, and configures a fixed local installation. It never executes app-writable checkout code or Compose. Its only listener is a restricted Unix socket; the app has a read-only runtime-directory bind, no root privileges or Docker socket. `maintenance_protocol.py` uses peer checks, timestamp/nonce HMAC authentication, bounded requests and strict predefined operation/field validation. The helper independently checks the root-held session/CSRF confirmation before restore and copies controlled source IDs through pinned no-follow descriptors.

The existing restore engine gains progress callbacks and authenticated write freeze/release. Helper-accepted jobs persist before acknowledgement and are keyed for replay. The helper survives app shutdown, retains the tested runtime lease/journal/marker/four-directory cutover/rollback, verifies restart/maintenance release, and recovers interrupted operations after its own restart. Browser polling resumes through the app once it is healthy; no detailed progress is claimed while that proxy is offline. Root administrator/session state and backup scheduling survive cultivation restores. An unresolved recovery fails closed. Host CLI and root-owned emergency tools remain available if the browser cannot reconnect.

Administrator passphrases use salted scrypt; random session tokens are hashed at rest, scoped to the backup API and expire after 30 minutes. A one-time deployment code protects initial setup, with per-client/global retry limits. Ordinary cultivation authentication is unchanged. HTTP/private-network and Docker-capable root-helper trust limitations are explicit in [2D.2 setup and recovery](MILESTONE_2D2.md). No application database migration, ZIP format change, cloud service or scheduler container is added.


### Passwordless trusted LAN policy

`backup_policy.py` is a standard-library policy shared by Settings and the root helper. `CULTIVATINATOR_BACKUP_AUTH_MODE` defaults to `password`; an explicit `trusted_lan` policy requires canonical, bounded CIDRs in `CULTIVATINATOR_TRUSTED_NETWORKS`. The opt-in `.env.trusted-lan.example` targets `192.168.68.0/24` without changing new-install defaults. The installer freezes the resolved mode/networks with Compose configuration; policy mismatch fails closed. No application schema or backup format changes.

Trusted browser access checks the actual peer and rejects forwarding headers. `server.py` disables Uvicorn proxy rewriting only for trusted_lan; password-mode behavior is retained. Host checks restrict passwordless administration to configured IPs/private hostnames to prevent DNS rebinding. Origin/Fetch Metadata guards remain. The Unix helper issues IP-bound expiring sessions and CSRF credentials after network verification, validates those credentials again for privileged operations, and stores trusted sessions separately from untouched password credentials. The UI opens/renews sessions without passwords and preserves destructive confirmation. Switching back to password mode restores the existing password workflow; tokens cannot cross modes. Root-only channel credentials, UID/GID, Docker isolation, restore validation/rollback, scheduling/retention and four-directory scope are unchanged. See [2D.2 configuration and boundaries](MILESTONE_2D2.md#password-and-trusted-lan-authentication-modes).
