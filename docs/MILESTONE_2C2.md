# Milestone 2C.2 — preparation, inoculation and transactional inventory

This increment implements agar, LC containers/syringes and grain spawn jars/bags. Actual spawning and FR tray/substrate allocation remain **2C.3**. It starts from merged PR #4 (`75b0a42`). No production server was accessed, merged or deployed.

The user-confirmed Debian layout is **`/storage/tv/cultivatinator` for the Git checkout, Compose configuration and persistent application storage together**, with that directory mounted at `/data`. Preserve this arrangement, port **8085**, the single-worker application and non-root UID/GID **10001:10001**. Do not interpret older examples that separated checkout/storage as an instruction to move this installation. The cloud development checkout remains `/workspace/Cultivatinator` with its separate ignored native `data/` directory.

## Stock and reusable pools

Inventory offers **+ Add Inventory**, **Stock & Pools**, **Prepared Materials → Prepare Materials**, and **Transactions**, alongside the unchanged outside Receive Acquisition workflow. Add Inventory records actual item names, category, quantity/unit, optional storage location/notes and a required reason. Categories are Reusable Containers, Raw Ingredients, Disposable Supplies, Equipment and Other Supplies. No examples or suggested counts are seeded or prefilled. Empty reusable pools require known whole counts. Grain bags and LC syringes use disposable count-based supplies. Fruiting tray inventory can be recorded, but spawning does not reserve it until 2C.3.

Supported weight units are mg, g, kg, weight oz and lb; volume units are mL, L, **US** fluid oz and **US** cups. Each/count and existing specialized counts remain available. Compatible conversions use precise Decimal factors: 1 lb = 453.59237 g, 1 weight oz = 28.349523125 g, 1 US fluid oz = 29.5735295625 mL. Weight and volume never convert into one another. Newly introduced units normalize opening balances to g/mL/count; existing g/kg/mL/L balances retain their unit. Ingredients and measured corrections can use compatible units, with original entered amounts/units retained in the operation audit. Conversion cannot bypass stock checks. Inputs and recipe scaling support three decimal places in the entered unit; converted balances and ledger entries retain all resulting precision.

Reusable pool tables distinguish Available Empty Containers, prepared Ready, inoculated Active Cultures / Spawn and historical Preparing reservations. For example, 7 empty + 5 ready + 8 active = 20 containers. Totals use only unreleased reservations, not historical preparation counts. Permanent IDs survive equipment reuse; terminal records and their batch snapshots remain accessible.

- Raw ingredients, consumables and biological source balances may be unknown. Usage is recorded while the remaining balance stays unknown.
- Reusable pools require a known free count: capacity cannot be safely reserved against an unknown number. Reservations deduct free capacity; one allocation is retained per prepared record until explicit completion/failure.
- Additions require a positive quantity and reason. Adding to unknown stock leaves it unknown. A documented measured **correction** establishes or changes a balance; source/raw balances may also be corrected back to unknown.
- Adjustments use the currently read inventory revision. A concurrent change produces 409 rather than overwriting a newer balance. Pool corrections mean **free, unreserved** count, not total owned count.
- Existing 2A/2B Starting/Registered Quantities remain descriptive. They are never copied into balances. LC jar/syringe details show **Remaining Culture Material** and a reasoned measured correction form. Unknown stays unknown until explicitly measured; a known zero depletes the source. Culture quantities are separate from generic physical supplies.

## Recipes and preparation

Open **Recipes** in the main navigation to save an agar, grain, LC or substrate-definition recipe with ingredient inventory IDs, quantities/units and a declared yield in **containers**. Optional instructions, processing defaults and shelf life are retained. Editing or archiving a recipe requires its current revision and never rewrites prior batches. Archived recipes remain readable but cannot prepare new material.

Select two or more recipe variants to compare ingredient amounts, yields, processing and shelf life. Substrate definitions support planning only; they cannot prepare materials, deduct substrate or allocate fruiting containers in 2C.2.

**Prepare in Inventory → Prepared Materials → Prepare Materials. Inoculate through Dashboard Quick Create.** Quick Create and Create From This keep their existing URLs and source context, with no preparation toggle or duplicate preparation fields. Empty Quick Create inventory says **No prepared containers available.** and links to the Inventory preparation page.

Preparation can proceed without a biological source:

1. Choose type/count (up to 100), matching reusable pool or disposable supply, and a saved recipe or actual manual ingredient quantities. Empty syringe preparation consumes syringe supplies without inventing media ingredients.
2. Recipe amounts scale by target count/yield; review/edit actual quantities. Scaling uses integer-thousandth previews and Decimal server arithmetic, rounded half-up to three places. A scaled amount below supported precision is rejected; count-based quantities must still be integral.
3. Record optional preparation date, method (pressure cooker, Instant Pot, pasteurization or custom), minutes, °C, psi, processing notes, batch notes, shelf life and use-by override. With a known preparation date, recipe/batch shelf life derives a use-by date unless explicitly overridden. No date is fabricated if preparation date is unknown.
4. One transaction checks stock, consumes actual ingredients/disposable supplies, reserves reusable capacity and creates a PB session with individual permanent **AG/LC/SJ/SB** identities.
5. Saving assumes preparation/sterilization is complete and creates **Ready to Inoculate** records atomically. No separate confirmation is required for new materials. Historical **Preparing** rows retain their explicit readiness action in the list/detail, without recreation, new deductions, snapshot changes or altered timestamps. Expiry is a visible warning, never an automatic discard/failure.

Prepared material has its own table until it has a biological identity. IDs are allocated using the existing sequence and retained on inoculation; a physical record is not assigned a fabricated strain or culture line during media preparation. Batch snapshots preserve original recipe/version, actual ingredient quantities/names, processing/settings and dates, independently of later recipe changes.

## Inoculation, transfers and filling

Select Ready to Inoculate containers, an eligible existing source, an optional date/notes and per-container source usage. Partial prepared batches remain ready for later use. Known source stock requires measured usage; LC requires a positive measured volume per destination, using mL or a compatible volume unit. Unknown agar/spore usage may remain unmeasured and is recorded as such. Selected count and total usage are displayed before submission.

| Destination | Sources |
| --- | --- |
| Agar plate | Active usable agar/slant, LC or spores |
| LC container / jar | Active usable agar/slant or LC |
| LC syringe | Active usable LC |
| Spawn jar / bag | Active usable agar/slant or LC |

Archived, completed, failed, depleted and zero-known-stock sources are rejected by the backend and omitted from Quick Create. Active registration is not proof of biological viability; the operator still confirms suitability. Exact source kind/ID, date, usage and shared operation are stored for each destination. Routine transfers retain the source's existing strain/line, without genetic-parent or new-line creation. New spawn starts **Colonizing**, not Ready for Spawning. The existing spawn stage edit provides an explicit Ready for Spawning selection later; this is separate from readiness of sterile prepared material.

Five bags at 5 mL each deduct **25 mL once**, create five independent SB biological records using their prepared IDs and retain the shared session. A failure at any point rolls back every row, deduction, reservation and sequence change. Donor agar remains active after transfer until explicitly completed/failed.

Filled syringes receive the measured transferred mL as their known opening balance. LC jars may receive a separately measured total destination volume; otherwise their remaining volume stays unknown. A supplied total cannot be less than the measured inoculum, and a syringe's filled volume must equal its transfer volume. No initial legacy quantity is used to manufacture a balance.

### Spores are pending establishments

Inoculating prepared agar from spores records physical inoculation and reserves the plate, but creates **no culture line** and asserts no confirmed genetic parent. On each pending plate's Prepared Material detail, **Register Successful Culture** invokes the existing dedicated Establish Culture operation. Only after success is confirmed does it create an independent CL and bind that plate's existing AG identity. Two plates from one print can establish two independent lines. It rejects binding an unrelated spore source, a failed/completed plate or a plate already established. Existing tissue-clone, isolate and standalone spore establishment workflows remain available.

## Depletion, lifecycle and history

A measured LC balance reaching zero sets **Depleted** automatically and excludes it as a source. It does not silently release its reusable container. A measured corrective adjustment, with reason/revision, can restore a depleted record's availability; unknown balances are never depleted solely from assumed usage.

Use **Complete** or **Mark Failed**, with date/reason/notes, on a prepared detail or supported biological physical/spawn detail. These preserve IDs, relationships, photographs and activity, release tracked reusable capacity **once**, and prevent subsequent source use. Terminal source inventory is closed while retaining its last recorded balance; correcting history does not reactivate a completed/failed culture. Archive/restore remains separate and does not release equipment or reset operational lifecycle. Active dashboard culture/spawn counts exclude terminal/depleted material.

Inventory Transactions displays append-only opening/add/correction/consume/reserve/release/usage/closure entries, before/after quantities (including unknown), reasons and operation IDs. Operation sessions also retain full dates/reasons/notes and selected prepared IDs. Record details link back to preparation snapshots and exact physical transfer sources/destinations. Existing galleries work for inoculated physical/spawn records and successfully established plates; uninoculated/pending prepared material has no separate photo storage/gallery. Tracked material types cannot be silently reassigned after preparation/balance tracking begins; ordinary descriptive editing remains available.

## Transaction and compatibility guarantees

- Python `Decimal` preserves compatible-unit conversion precision. Nullable exact text sidecars hold authoritative new balances and ledger quantities in SQLite; legacy Numeric(14,3) columns remain compatibility projections. Historical rows fall back to their original Numeric values, without backfill or ledger updates. All availability, depletion, deduction, adjustment and release decisions read exact balances. Frontend scaling previews use integer thousandths; the server validates actual converted deductions.
- All command endpoints require a stable `request_key`. `BEGIN IMMEDIATE` serializes reads/decisions/writes. A repeated identical request replays its committed response; reuse with different payloads returns 409. Failed requests commit nothing. The UI retains a key when retrying unchanged input and supports ordinary private-network HTTP without depending on secure-context-only `randomUUID()`.
- Revision checks protect stock/recipe edits. A unique transfer per prepared record prevents reinoculation under a new key. Terminal lifecycle checks and one reservation-release flag prevent a second release, even with a different key. Immutable SQLite guards protect committed audit records, snapshots and transfer sources.
- `0005_preparation` adds nine tables: `stock_items`, `stock_transactions`, `inventory_operations`, `preparation_recipes`, `preparation_batches`, `prepared_materials`, `container_reservations`, `material_lifecycles`, `material_transfers`. `0006_history` adds committed-history guards. `0007_inventory` adds optional storage, Equipment/Other categories and nullable exact quantity sidecars, retaining all existing rows, IDs, constraints, history guards and reservations. SQLite rebuilds only the stock table to expand its category constraint and verifies foreign keys afterward. No existing migration is edited. No 2B rows/IDs/photos are rewritten or backfilled into known inventory.
- Lifecycle and inventory links are additive projections on existing record APIs; archive status and starting quantity fields keep their original meanings. FR known/mixed/partial/unknown strain derivation and genetic/grow provenance remain unchanged. 2C.1 redirects and Inventory acquisition paths remain compatible.

Typed APIs are documented at `/docs`. Inventory/preparation endpoints under `/api/preparation` include `pools` (read-only reconciliation), `stock`, `stock/{id}/adjust`, `recipes`, `recipes/{id}`, `prepare`, `ready`, `inoculate`, `materials`, `materials/{id}`, `materials/{id}/finish`, `records/{kind}/{id}/finish`, `records/{kind}/{id}`, `transactions`, and `operations`. Existing spore establishment adds optional `prepared_id`; it is valid only for a matching pending spore-inoculated agar record.

## Validation commands

```bash
cd /workspace/Cultivatinator
(cd backend && ../.venv/bin/pytest -q && ../.venv/bin/alembic upgrade head && ../.venv/bin/alembic current && ../.venv/bin/alembic check)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/preparation_browser_smoke.py /usr/bin/chromium
# Optional managed-proxy CA build mount; TLS verification stays enabled.
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t cultivatinator:milestone-2c2 .
.venv/bin/python scripts/preparation_docker_smoke.py cultivatinator:milestone-2c2
```

Browser tests use separate temporary data directories; Docker smoke uses and removes only its unique disposable container/volume. They never mount Debian data. The 2C.2 browser check also simulates private-network HTTP without `randomUUID`. Docker recreation checks persistent recipes/prepared snapshots, stock, immutable ledger, depletion, one-time release, retry replay and original 2B photos/FR relationships. Final usability-correction validation: **96 backend tests passed** (one existing upstream Starlette/AnyIO deprecation warning), **58 frontend tests passed** across six files, and the production build passed. Fresh/repeated Alembic upgrade, current and schema check passed at **0007_inventory** with no drift; the regression suite also upgrades a populated 0006 database while preserving its legacy Preparing row, reservation, timestamps, immutable ledger/snapshot and old request-key replay. All four browser smoke scripts passed, including generic imperial-unit inventory, recipe variant comparison, Inventory preparation, automatic readiness, partial inoculation, source preselection, exact depletion/correction, pool reconciliation and desktop/mobile layouts. Docker build and non-root recreation/persistence checks passed with retained accounting, lineage, FR identity and photographs. No final test or build failures remain. GitHub API metadata access returned Forbidden in the cloud session; delivery updates the existing PR branch through Git push.

## Safe Debian upgrade and rollback — manual only

The checkout, Compose configuration **and data coexist** at `/storage/tv/cultivatinator`. Do not relocate them, delete directories, run a clean/reset across the checkout, or recursively change ownership of the entire mixed source/data directory. Preserve existing ownership; only application data subdirectories need the existing UID/GID 10001 access. `.dockerignore` now excludes root `database/`, `photos/`, `files/`, and `settings/` from build context, in addition to `data/` and `.env`; it does not remove or move those directories or change the `/data` bind mount.

The current Debian installation contains dummy test data; the user does not require backups for routine testing. This correction performs no destructive reset and does not access or deploy to Debian. The following optional stopped-data procedure is retained for installations where data preservation is needed.

Before such a deployment, record the current image/tag, Git commit and exact Compose project/configuration, preserve `.env` securely, and confirm the running container's `/data` mount actually points at `/storage/tv/cultivatinator`. Stop the application and archive the **entire co-located directory**, including `.git`, Compose/configuration, database and WAL/SHM sidecars, photos, files and settings. Store the archive outside the source/data directory, verify it, and keep an off-server copy plus the old image. For example, after selecting the actual existing container:

```bash
set -eu
container_id=ACTUAL_EXISTING_CULTIVATINATOR_CONTAINER_ID
sudo docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$container_id"
# Stop if the mount differs; inspect instead of guessing.
sudo install -d -m 0700 /storage/tv/cultivatinator-backups
backup_file="/storage/tv/cultivatinator-backups/pre-2c2-$(date +%Y%m%d-%H%M%S).tar.gz"
old_image=$(sudo docker inspect --format '{{.Image}}' "$container_id")
sudo docker tag "$old_image" "cultivatinator:pre-2c2-$(date +%Y%m%d-%H%M%S)"
sudo docker stop "$container_id"
sudo tar -C /storage/tv/cultivatinator -czf "$backup_file" .
sudo tar -tzf "$backup_file" >/dev/null
sudo sha256sum "$backup_file"
```

If using this optional backup procedure, do not rely on an archive after any backup failure. Copy the verified archive/image information off-server. Inspect `git status --short` and preserve local changes before updating to the reviewed code; use the existing Compose project/options and port setting. Migrations run before accepting requests. A migration failure is a blocker: preserve logs/data and diagnose rather than resetting Alembic or deleting the database. This task does not execute deployment.

Rollback requires the **matching pre-upgrade application and stopped-data backup**. Stop writes, preserve the entire post-upgrade co-located directory separately, and test restoration into a separate directory before changing the existing installation. Ensure a test's `/data` points at its restored copy, not the absolute live path from a copied `.env`/Compose file. Preserve source/configuration and data together when restoring the final original arrangement. Do not extract over an active or newer database, and do not run an old image against the upgraded database. Downgrade guards refuse to discard preparation/inventory history. New records since backup would not be present in that older snapshot.

## Deferred to 2C.3

Actual spawn-to-bulk consumption, FR tray/substrate allocation, editable spawn/substrate ratios, prepared bulk-substrate accounting, harvest/flush accounting, advanced observations, bulk observations and downstream contamination warnings are not implemented. Tray pools can be configured, not operationally assigned to an invented spawning event. Purchases/supply tracking beyond manual stock additions and the established external-acquisition workflow remain future work. No new services, authentication, synthetic strains, automatic merge or production deployment are introduced.
