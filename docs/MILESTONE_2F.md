# Milestone 2F — Experimental Genetics

## Workspace and workflows

Genetics adds the Adaptive Photo Tree to the existing Industrial Monitoring Console. **Strain Family** defaults to the first catalog strain and displays its recorded culture lines. **Magic Kingdom** organizes the whole collection by named strain, with a separate Unknown Strain group. Empty catalog strains remain represented. Strain headings are browsing groups, never genetic parents. Multiple independent roots remain independent; archived lines remain visible with dashed card borders and explicit Archived labels.

Select a photo card or use the relationship list to inspect a culture's permanent ID, status, origin, recorded parents and confidence, immediate descendants, original spore/fruiting source and associated photographs. Open Record returns to the existing library. Search includes names, permanent IDs, archived cultures and unknown identities across the entire collection. Focus on This Family switches views and centers that culture. View, strain and selected culture are URL parameters, preserving normal back/forward navigation and links. Camera and branch collapse are temporary view state.

Drag to pan, use the wheel or Zoom In/Out, and use Fit to Screen or Reset View. Touch gestures support panning and two-finger zoom. Arrow keys pan the focused canvas; plus/minus zoom. All controls and culture selections are native keyboard controls. The relationship-list alternative exposes parent confidence as text. Desktop places details beside the canvas; narrower screens stack details below it. Reduced-motion preferences disable card transitions; navigation never relies on animation.

Close zoom displays photographs, names, permanent IDs, origin labels, status and ancestry confidence. Medium zoom uses portraits with shorter labels and origin labels; far zoom uses compact thumbnail/icon nodes. Cell positions do not change when detail level changes, preserving selection context. At far kingdom zoom, families aggregate into photographic summary regions with counts and a Focus on This Family action rather than rendering hundreds of tiny text cards. Search and selected details remain available while aggregated.

Create Isolate opens the existing establishment form for an active line. Establish Tissue Clone appears only when actual, active associated fruiting records exist; the user must choose one. Eligibility deliberately follows existing establishment rules, without adding a new biological eligibility policy. The original endpoint validates the source again at save time. Successful establishment refreshes the graph, selects and centers the new descendant, and stays in Genetics. A culture node is never used directly as a tissue source. Mixed physical sources retain their existing possible-parent semantics.

## Genetic truth and retrieval

`GET /api/genetics` returns the catalog strains, culture nodes, thumbnail references, associated photos, actual active fruiting-source options and the current `LineParent` edges. The query uses eleven bulk SQL statements independent of node count; it does not call the provenance or photo API once per node. Selecting an establishment action loads that one existing record and the existing provenance form. The graph refreshes on mount, return navigation, window focus and successful local writes; there is no polling service.

Only `LineParent` produces edges: confirmed parents use solid paths, possible parents use dashed paths and explicit text. Roots say Unknown ancestry when no genetic parent is recorded. Current `LineOrigin` supplies acquired, isolate, clone and spore-derived labels and original source links. Cross-family relationships are shown only when explicitly recorded; family view lists parents outside the displayed family with a Different strain family indicator. Historical ancestry, revision checks, cycle prevention, and correction activity remain in the existing validated provenance workflows. This read endpoint does not edit biological records. Routine transfers, spawn sources, mixed allocations and fruiting membership determine eligible physical source/photo associations, never new genetic edges.

The dependency-free layout assigns deterministic depth from recorded parent edges and stable row positions. Multiple possible parents remain a graph. Collapse hides a descendant only when all its displayed incoming branches are collapsed/hidden, preserving shared descendants reachable from another visible parent. Fit uses the visible layout. Pure layout tests exercise 600 culture lines; kingdom aggregation limits canvas rendering when zoomed far out. Retrieval still loads the collection and associated thumbnail metadata in one response; this is intended for hundreds of lines, not an unbounded media catalog. Search shows up to 25 matching results; refine the search when more match. Large installations may eventually justify server-side search and photo pagination.

No graph dependency, background service or new database table was introduced. Existing frontend and Docker lockfiles remain unchanged.

## Photograph selection and persistence

Priority is:

1. Culture line cover photo.
2. Explicit representative selected from that line's existing line/physical culture/spawn/associated fruiting photographs.
3. Strain cover photo, explicitly marked as a family fallback rather than the culture's own image.
4. Neutral genetics icon.

Use as Genetic Tree Photo references an existing attachment; it never copies a file, changes the owner or overrides a line cover. The gallery identifies each original permanent owner ID. Clear representative photo removes the preference. Archived source photos remain usable historical documentation. Deleted attachments, missing originals/thumbnails and associations invalidated by later provenance changes are ignored and fall back safely. The browser also replaces failed image loads with a neutral icon.

`PUT /api/genetics/lines/{code}/photo` accepts `{ "photo_id": "attachment UUID" }` or null to clear. It validates the line and current photo association on the server. A strain cover or unrelated attachment cannot be selected as the line's representative. Preferences are atomically written and fsynced to `settings/genetics.json`, version 1, mapping line IDs to attachment IDs. Existing mutation fencing serializes writes. Read failures, unsupported versions, symlinks and files larger than 2 MB yield a visible 503; reads never silently overwrite corrupt data. Repair/restore that specific settings file while stopped rather than deleting the database.

This small display preference uses the existing backed-up settings mechanism, like dashboard preferences, so no Alembic migration or archive schema change is necessary. Existing backups already include settings and photos. Automated backup verification/extraction and app restart tests prove representative choices and their original photos round-trip together. A backup without this file uses normal cover/icon fallback. Old app versions ignore the file.

## Validation

Commands from the repository root:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test -- --maxWorkers=2 && npm run build)
.venv/bin/python scripts/genetics_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/dashboard_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/reports_browser_smoke.py /usr/bin/chromium
docker build -t cultivatinator:milestone-2f .
.venv/bin/python scripts/backup_docker_smoke.py cultivatinator:milestone-2f
```

Managed proxy builds can supply the existing optional `proxy_ca` build secret; TLS verification remains enabled. Playwright/Chromium are optional acceptance tools, not application runtime dependencies.

Validation during implementation: 316 backend tests and 185 frontend tests passed; production frontend and Docker builds passed. Fresh and repeated Alembic upgrades and schema-drift checks passed at unchanged head `0013_journal_photos`. Genetics browser checks cover independent roots, photographs, archived records, collapse, all zoom detail levels, isolate/recorded-fruiting clone creation and refresh, kingdom search/family focus, desktop panning/wheel, keyboard, mobile touch and reduced motion. Existing lineage, dashboard, Quick Create and Reports browser suites passed. The dashboard smoke needed a retry under concurrent build/test load. One existing Starlette/AnyIO deprecation warning remains.

The real host-CLI Docker backup test verified its checksummed archive but could not complete its injected-failure rollback: the managed environment denies inspection of `/proc/1/fd/0`, required by the existing host writer-fencing code. This is an environment limitation, not a passing restore acceptance result. The safety check was not disabled or bypassed. Full privileged host/browser restore acceptance remains to run in a suitable isolated Docker host; no live Debian restore was attempted. Backend backup/restore tests, including the new representative-photo round trip, pass.

## Debian review, deployment and rollback

No Debian deployment, merge, helper reconfiguration or environment publication is performed by this milestone. Review the feature branch/PR first. On the existing installation, create, verify and download a backup; preserve local Git edits, Compose, `.env`, storage ownership and all maintenance/Trusted LAN settings. Fetch and select the reviewed code through the existing checkout, then rebuild the existing Dockge/Compose app using its established management path. Do not create a second project against the same data directory. Check `/api/health`, existing records and photographs, then the Genetics workspace on desktop and mobile.

There are no database migrations, dependency updates, helper protocol changes or cultivation accounting changes. Existing schema stays `0013_journal_photos`. No helper reinstall is required for this display-only milestone. Rollback consists of selecting the previously reviewed code and rebuilding that same app; preserve data and `settings/genetics.json`. Older code ignores the new preference file. Do not reset the database or copy source/configuration over the co-located data root. If a host-level restore is needed, use the existing documented stopped-data workflow and verified backup; never restore solely to roll back this UI.
