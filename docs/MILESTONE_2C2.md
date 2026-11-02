# Milestone 2C.2 — direct cultivation and recipes

This final workflow redesign supersedes the earlier inventory-first and prepare-first interfaces on `feature/milestone-2c2-preparation` (existing PR #5). Cultivation tracking is the primary workflow. No deployment or merge is part of this task.

## Quick Create

Choose Agar Plate, Spawn Jar/Bag, LC Container/Jar or LC Syringe. Select a matching active recipe, biological source, number of containers and date; the date defaults to the browser's current local date and can be changed. Add optional notes and measured source usage when applicable. **Saving means preparation, sterilization and inoculation are already complete.** No ingredient inventory, container pool, reservation or separate readiness operation is required.

Agar requires an agar recipe. Spawn uses grain recipes from Spawn Seed. LC jars use LC media recipes; filling a syringe from existing LC does not require a media recipe. Recipe definitions have named ingredients, quantities and units, without requiring stock entries. Existing inventory-linked recipes remain compatible; direct creation never deducts their ingredient stock or fabricates a balance.

One atomic, idempotent operation assigns independent AG/LC/SJ/SB IDs, snapshots the recipe/version and batch quantities, records the inoculation date and exact physical source, and creates inoculated records. A routine transfer preserves its source's culture line. New spawn starts **Colonizing**, with Ready for Spawning still an explicit later edit. Failures roll back every destination, source deduction, snapshot and ID allocation. Retries replay the committed response; Create More starts a distinct request.

The completion screen prominently lists every permanent ID, links to each record and provides Copy IDs plus selectable text for browsers without clipboard access. The ID belongs to the biological record, not a piece of reusable equipment.

Spores create individual pending agar establishments with permanent AG IDs and physical spore provenance, without a genetic-line assertion. Open each pending record and use Register Successful Culture after success is confirmed. Each establishment creates an independent line through the existing workflow.

## Recipes workspace

The main Recipes landing page has exactly three category cards: **Agar**, **Spawn Seed**, and **Substrate**. Each opens its own list, with a prominent Add Recipe action, descriptions, links to details and variant comparison. Spawn Seed separates **Grain spawn** and **Liquid culture media** using a subtype filter; no fourth category is introduced. No example recipes are seeded.

Recipe details display ingredients/units, yield in containers, instructions, processing settings, notes and last update time. Historical recipes without an edit timestamp show that it was not recorded; their original creation time remains available.

- Edit Recipe preserves earlier cultivation/preparation snapshots and uses revision conflict protection.
- Duplicate Recipe creates an active editable copy with a new recipe ID.
- Delete Recipe permanently deletes only unused definitions after explicit browser confirmation. An immutable operation audit remains. A used recipe cannot be deleted; Archive hides it from new creation while preserving historical links and snapshots.
- Substrate definitions support the same management actions, but cannot execute preparation, consumption or fruiting allocation in 2C.2.

## Growing workspaces

Laboratory lists active agar, liquid cultures and pending spore establishments. Cultivation lists colonizing jars/bags and spawn ready for use. Filters expose completed, failed and all historical records; IDs, strain, culture line, source, status and recorded dates remain visible. Search by ID, strain or line. Record links retain the existing photo galleries, activity, genetic genealogy and physical provenance, and now show their recipe snapshot/source history directly.

Culture Library remains the reference/catalog area. Existing acquisitions, clones, isolates, spore collection, archive/restore, FR strain identification and legacy URL redirects remain available.

## Optional inventory and LC volumes

Inventory shows actual optional ingredients/supplies immediately after saving, with category, quantity, unit and location. Edit changes name, location and notes without changing the balance; Adjust Quantity records additions or measured corrections with a reason. Accounting/history and old reusable pools are secondary views, not prerequisites for culture creation.

Existing precise Decimal conversions remain: mg/g/kg/weight oz/lb, mL/L/US fluid oz/US cups, each/count and specialized counts. Weight never converts to volume. Exact quantity sidecars retain conversion precision in SQLite alongside legacy Numeric projections. Unknown balances remain unknown.

LC details retain **Remaining Culture Material** and reasoned measured corrections. Known source balances require measured usage, are checked atomically and are deducted once across the batch. For example, five bags at 4 mL use 20 mL; 100 mL becomes 80 mL. Zero-known LC is Depleted and excluded from source choices. Unknown LC may record unmeasured use for agar/jars/spawn without manufacturing a remaining quantity; filling syringes requires a measured transferred volume. Filled syringes receive that measured opening balance; LC jar destination totals are optional measured values.

## Historical preparation compatibility

All existing stock, immutable accounting, prepared records, reservations, permanent IDs and snapshots are retained. Previous preparation/accounting links remain accessible from Inventory, Laboratory and Cultivation. Historical Preparing records retain their explicit readiness transition without recreation, new deductions or changed timestamps. **Inoculate Previous Materials** completes ready records using their original IDs and existing allocations. Complete/Failed releases an existing tracked reusable reservation once. Newly created direct records have no container reservation to release.

Internally, direct creation reuses the immutable preparation-batch snapshot and per-destination physical transfer tables in the same transaction. Intermediate material rows are never exposed as a separately required preparation step; successful direct operations commit them as inoculated. No synthetic strains, genetic parents or culture lines are introduced by ordinary transfers.

## API and migration compatibility

Existing `/api/preparation` and library/provenance APIs remain compatible. Additions include `POST /create`, `GET /growing?workspace=laboratory|cultivation`, recipe detail/delete/duplicate endpoints, and `PUT /stock/{id}` for metadata edits. Recipe ingredients accept either existing stock IDs or independently named ingredients. Historical inventory preparation still requires inventory-linked ingredients because it performs actual deductions; it never guesses stock links for named formulas.

Migration **0008_recipes** adds only nullable `preparation_recipes.updated_at`. Prior migrations are unchanged. Existing recipe contents, preparation stages, timestamps, operations, ledger entries, IDs, photographs and lineage are not rewritten. Old recipe and stock request keys retain their original fingerprints. Downgrade guards refuse to discard recorded recipe edit history or operational accounting.

## Validation

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/preparation_browser_smoke.py /usr/bin/chromium
```

Validation uses temporary databases, local Chromium and uniquely named disposable Docker resources. No Debian data is accessed. Final verification: **114 backend tests passed**, **71 frontend tests passed** across seven files, and the production build passed. Alembic fresh/repeated upgrade, current and check passed at **0008_recipes** with no schema drift; tests cover populated 0006/0007 upgrades, unchanged historical snapshots and old request-key replay. All four browser suites passed with no page errors, including the full final workflow and mobile layouts. Local Docker build and non-root recreation checks passed for direct records, free-standing recipes, existing prepared material, stock/ledger, photographs, FR identity and lineage. One existing upstream Starlette/AnyIO deprecation warning remains; no final test/build failures remain. GitHub API metadata access returned Forbidden; delivery updates PR #5 through its existing Git branch.

## Debian installation context

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

Actual spawn-to-bulk operations, fruiting substrate allocation and ratios, harvests/flushes, advanced dated growth observations, contamination propagation and detailed analytics remain deferred. Substrate recipes are definitions only. No production deployment or merge is performed.
