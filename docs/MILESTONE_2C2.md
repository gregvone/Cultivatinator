# Milestone 2C.2 — final cultivation-focused simplification

This revision supersedes the earlier 2C.2 inventory and three-category recipe interfaces on `feature/milestone-2c2-preparation` (existing PR #5). Cultivatinator tracks cultures and cultivation history; no Inventory workspace, empty equipment setup, prepared-material creation or ingredient accounting is required in the normal interface.

## Navigation and acquisitions

Main navigation now provides **Acquisitions** in place of Inventory. Receive Acquisition uses the existing universal backend for outside cultures, agar, LC, spores, spawn and ready-to-fruit material, preserving supplier, origin, acquisition date, strain and source relationships. Receiving outside material does not claim that the user prepared or inoculated it.

**Add Strain** is a single clear action in Culture Library and creates only a reference identity. The library retains its catalog, genealogy, provenance, photographs, edit/archive and history interfaces.

Legacy acquisition URLs, including `/inventory/receive-acquisition`, `/culture-library/acquire` and typed receive-culture/receive-spores URLs, redirect to Acquisitions with query/hash context retained. Old strain URLs redirect to Culture Library. Old prepared-material URLs redirect to historical material pages. Generic Inventory/stock URLs no longer expose supply management.

## Four recipe categories

Recipes has exactly **LC Media**, **Agar**, **Spawn Seed** and **Substrate**. Agar, grain and substrate have independent lists, descriptions, details, comparison, add/edit/duplicate, delete-unused confirmation and archive-used controls. Ingredients are named quantities with common weight/count/volume units and do not require inventory links. Detail pages show category, description, ingredient amounts/units, yield, instructions, processing, notes and creation/update dates.

Used definitions retain immutable cultivation/preparation snapshots. Editing or archiving cannot change past formulations. An unused non-default recipe can be permanently deleted after confirmation; used recipes are archived instead. Prior recipes and their IDs remain intact.

## One designated default LC Media recipe

LC Media opens its designated default formula directly. If none is configured, **Set Up LC Media** leads to a blank formulation; no ingredients are invented. Save the formula and explicitly choose **Use as Default LC Media**. Existing LC definitions remain available for designation through the management link. Only one active default is designated at a time, with atomic revision-checked selection.

New LC jars/containers automatically use the designated default and save its exact recipe/version snapshot. Their form has **no media recipe selector**. If setup is missing, the form links to LC Media and waits for one-time configuration. Editing the default changes future operations only. Archiving it clears the designation and requires a new active default for subsequent jars. A designated default cannot be silently retyped or permanently deleted.

Filled LC syringes have **no recipe input and no default-setup requirement**. They retain culture identity and the source LC's actual immutable media snapshot/version where known, including when the definition is later edited, replaced or archived. They record media transfer, no ingredient consumption, no new media processing and no media preparation date. An acquired source without recorded formulation remains unknown; the current default is never used to invent its past medium.

## Quick Create and permanent IDs

Save after material is already prepared, sterilized and inoculated. Agar selects an active agar recipe and compatible source. Spawn chooses Jar/Bag, a grain Spawn Seed recipe and an eligible agar/LC source. LC jars choose a source, count and optional measured starting volume; default media is automatic. Syringes choose an LC source, count and measured transferred volume. Local dates populate automatically and can be overridden. Notes and appropriate source usage remain available.

Every destination receives its own AG/LC/SJ/SB permanent ID through the existing allocator. Bulk creation is atomic; a failure rolls back all destinations, balances and ID allocations. Repeated submissions replay the committed result, even after a default recipe changes. Create More starts a distinct request. Completion prominently shows all IDs with copy/selectable-text and individual-record links.

**Create From This** on LC and agar records opens the appropriate Quick Create entry with the exact physical source preselected. Compatible sources/recipes are filtered, LC jars use the default automatically, and syringes never request media selection. Ordinary transfers preserve the genetic culture line and record exact physical source provenance. Spores remain independent pending establishments until the existing successful-culture workflow creates each line. New spawn starts **Colonizing**; Ready for Spawning is a later explicit action.

Spore-print collection remains unchanged. Actual spawning/fruiting execution remains deferred.

## LC remaining volume

LC jar/syringe details show **Remaining Culture Material** and a measured correction form with a reason. No Inventory visit is needed. Known source balances require measured usage, validate sufficient stock and deduct once across the bulk operation. Five bags at 5 mL deduct 25 mL; 100 mL becomes 75 mL. Zero-known LC becomes Depleted and cannot be reused. Corrections can restore a measured or unknown balance without reviving completed/failed cultures.

Unknown balances remain unknown. Filled syringes receive measured transferred volume; LC jar starting totals are optional measured quantities. Precise Decimal compatible-unit conversion, immutable usage audit, revision checks and idempotency remain functional independently of media-recipe selection. Initial acquisition quantities are never silently imported as remaining volume.

## Growing workspaces and historical compatibility

Laboratory lists active agar, LC and pending spore establishments. Cultivation lists colonizing jars/bags and ready spawn. Search/filter controls include completed, failed and archived history; rows show permanent IDs, known strain/line, source, recipe, dates and lifecycle. Record details retain photographs, history, genealogy and source/recipe snapshots.

Historical preparation data remains accessible through record history and `/history/materials`; old URLs redirect. Existing Preparing rows can transition to Ready without new deductions or altered timestamps; previously ready material can complete its existing inoculation using original IDs. Historical Complete/Failed releases tracked reservations once. Normal direct creation has no container reservations. Generic supply management and new preparation screens are absent from application navigation.

Existing accounting tables/APIs, transactions, preparation batches, reservations, snapshots and migrations are preserved, with no destructive reset. LC accounting continues using the existing precise ledger internally. These compatibility records do not impose new inventory requirements.

## API and migration changes

**0009_lc_default** adds only a singleton table referencing the explicitly designated LC recipe. No recipe is seeded, auto-selected or rewritten, and migrations 0005–0008 remain unchanged. SQLite enforces a single default row; the API requires an active LC definition and matching revision. Configured defaults persist across restarts and are protected from accidental destructive downgrade.

`GET/POST /api/preparation/lc-default` reads/designates the default. Direct LC jar creation requires it; an explicitly supplied legacy recipe ID must match it. Syringe creation resolves the source's recorded medium instead of selecting a recipe. Existing request keys replay committed results and historical recipe snapshots remain unchanged. Historical preparation APIs remain available without adding a default requirement to previously prepared material.

## Validation

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/preparation_browser_smoke.py /usr/bin/chromium
```

All checks use temporary local databases and disposable Docker resources. Final verification passed: **122 backend tests**, **79 frontend tests** across seven files, the production build, fresh/repeated Alembic upgrade/current/check at **0009_lc_default** with no schema drift, and all four browser smoke suites. Browser checks exercise all four LC Create From This actions, default setup, selector-free LC creation, inherited syringe media, 100 mL → 75 mL usage, Acquisitions, Add Strain, old URL redirects, historical prepared records, photographs/lineage and mobile layouts with no page errors. Local Docker build and non-root recreation/persistence checks passed, including the default designation, inherited media, balances, idempotent replay and existing FR/photos/history. Obsolete tests for generic Inventory/new-preparation UI were replaced; historical accounting compatibility tests remain. One existing upstream Starlette/AnyIO deprecation warning remains; no final test or build failures remain. GitHub API metadata access returned Forbidden, so PR delivery is verified through its existing Git branch. No Debian data is accessed.

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

Actual spawning, spawn-to-bulk consumption, fruiting substrate allocation/ratios, flushes/harvests, advanced observations, contamination propagation and detailed cultivation metrics remain deferred. Substrate definitions are fully manageable now. No merge or deployment is performed.
