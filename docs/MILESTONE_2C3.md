# Milestone 2C.3 — Fruiting, Flushes & Harvest Tracking

Implemented for Debian review on `feature/milestone-2c3-fruiting`, based on main merge `30791b64364e972d1a080468e4468586fe7c70f4`. No automatic merge or deployment.

## Practical workflow

Use Dashboard **New Fruiting Container**, Cultivation, or **Create From This** on Ready spawn. Select one Ready jar/bag, an active Substrate recipe, a container count and spawning date (local today, editable). Optional grams of spawn/substrate are **per destination**, descriptive measurements. No substrate stock, equipment registration or tent configuration is required.

A single operation consumes the selected spawn in full, divided across all destinations. Each FR has a separate permanent ID, automatic physical label and exact source link. Trays default to reusable F labels; bags/blocks have non-reusable FD labels. Optional available/new label overrides use the established allocator. The operation saves immutable recipe/version and optional environment snapshots. Spawn becomes Used once, releasing J where reusable; disposable B history never becomes reusable. Historical preparation reservations close once where present.

SQLite immediate-write transactions include all destinations, labels, provenance, snapshots and consumption. Failures roll back everything. Stable request keys replay committed results even after the donor becomes Used. A new browser submission checks current Ready eligibility; a retry of the same command preserves its original request key. No operation accepts multiple spawn sources. Database triggers prevent adding/replacing/removing the selected operational source. Existing mixed-source **manual 2B history** is retained; manual registration still does not consume spawn.

## Growing stages and harvests

**Colonizing → Pinning → Fruiting → Harvest**. New grows start Colonizing, with pending flush number 1 and no invented pinning/fruiting date. Mark Pinning and Mark Fruiting record explicit dates. Record Harvest starts Harvest; multiple entries can be saved over several days in that same flush. Next Flush creates the next numbered flush at Pinning with its actual date, then repeats Fruiting → Harvest.

Each harvest has its own permanent HR ID, date, optional wet/dry grams, optional subjective medicinal-potency rating (1–5), potency notes and special notes. The rating is a subjective grower assessment, not a laboratory assay or verified compound concentration. Dry weights can be added later, including after the grow ends. Edits require the current revision and append immutable snapshots; earlier measurements remain accessible under Measurement history. Negative/non-finite/over-precision weights and invalid ratings are rejected. Dates cannot precede known spawning/pinning/fruiting events, follow the next flush, or follow a known grow ending.

Multiple photos attach to their **exact harvest**, using the existing verified-image uploader, viewer, cover and removal controls. They also remain visible in the grow's gallery. Photo files, metadata and harvest links commit together; failures clean up new files. Cover selection continues to apply to the owning grow. Original FR photos and attachments remain intact.

**Finish Grow** is explicit when no further flushes are expected. It records date/optional notes, marks Completed, releases reusable F once and removes the record from active growing lists. Mark Failed is a separate terminal action with the same reusable-label boundary. Harvesting, starting another flush and editing dry weight never release F. Archiving remains a visibility action and never releases a label. Restore an archived record before recording new growing events. Historical harvest measurements and photos remain editable on completed/failed records.

## Photos while recording Pinning and Harvest

Mark Pinning, Next Flush and Record Harvest each offer an optional multiple-photo selector alongside the existing date and notes/measurements. The event or harvest saves first. Files then use the established validated image uploader. Pinning photos belong to the permanent FR ID, exact numbered flush and recorded Pinning event; harvest photos use the exact permanent HR ID. A Next Flush response supplies the new number, so its photos never fall back to flush 1 or follow a later current-flush change.

History displays each flush's Pinning date, full notes and small clickable thumbnails, followed by individual harvest measurements, notes and thumbnails. The same galleries support later uploads, cover selection and removal, including after grow completion. Photo edits never change a Pinning date or release a physical label. The general grow gallery remains available, but exact event relationships are retained separately.

If a photo fails after its record saved, the inline form clearly reports **Pinning saved for flush N** or **Harvest HR-… saved**, names the failed file and retains its pending upload. Retry remaining photos sends only remaining files to the saved target; it does not repeat the stage transition or create another harvest. Saved date/measurement fields are disabled during this continuation. Successful files are not resent. Users may remove an invalid pending file, select a replacement, or finish and add remaining pictures later. Temporary history-refresh failures keep the saved target and retry controls visible. Lost record-creation responses still replay the original request key before photo uploading starts.

**0012_pinning_photos**, following 0011, adds only nullable `fruiting_flushes.pinning_notes` and a `pinning_photos` relationship table. Composite foreign keys bind each photo to FR/flush; validation requires a recorded Pinning date and matching photo owner. Relationships cannot be reassigned. Removing a photo cascades its link and records the exact Pinning flush in activity history. Existing dates, photographs, harvest associations, files and 0011 migration remain unchanged; old notes are still preserved in activity history and are not guessed/backfilled into the new field. Downgrade refuses to discard new Pinning photo/note history.

`GET/POST /api/fruiting/records/{FR}/flushes/{number}/pinning/photos` lists/adds exact Pinning photos. The existing harvest-photo and global photo viewer/cover/removal APIs remain unchanged. Uploads remain separate from idempotent lifecycle/harvest commands so a file failure cannot erase an already saved event.

## One optional fruiting tent

Settings has one optional Fruiting Environment form: tent name, target temperature/unit, relative humidity, humidifier notes, FAE setting/schedule and general notes. Nothing is seeded. Revision-checked configuration changes affect future grow snapshots only.

Grow details show the effective environment, original immutable snapshot and optional dated changes. Record Environment Change appends settings and a reason/notes for that active grow. It neither changes the default nor rewrites earlier snapshots. There are no daily logs, sensor integrations, automatic controls, equipment maintenance, alerts or environmental charts.

## Results

Each grow displays flushes with harvests, known wet/dry totals, totals per flush, days from spawning to first recorded pinning/harvest, and completed cycle duration. Each weight total has a measured-entry count; unmeasured entries are not treated as zero. If no relevant measurement/date exists, its result stays Unknown. A measured zero remains zero. An unharvested flush does not count as a harvested flush. Timing uses actual recorded dates only.

The data retains source strain/culture-line provenance, substrate recipe ID/snapshot and environment snapshots for later comparisons. A large analytics dashboard is deferred.

## Additive migration and compatibility

**0011_fruiting**, following `0010_containers`, adds:

- `fruiting_runs`: operational source, originating command, immutable recipe/environment snapshots, quantities, spawning date, current stage/flush and terminal outcome.
- `fruiting_flushes`: numbered flushes with actual pinning/fruiting dates.
- `harvest_entries` and append-only `harvest_revisions`: measurements and full revision snapshots.
- `fruiting_environment` (singleton) and append-only `fruiting_environment_changes`.
- `harvest_photos`: exact links to existing photo attachments; removing a photo removes its link without deleting its harvest.

Typed foreign keys/checks, unique revisions, existing label indexes and source/snapshot history triggers protect relationships. Earlier migrations and existing photo/accounting tables are not rewritten. Downgrade refuses to discard fruiting history or configured settings; use a matching stopped-data backup with its matching application for rollback.

Legacy FR records are not backfilled. Reading them creates no run, flush, dates, recipe/environment association or source-consumption event. Their existing labels, photos, strains, mixed allocations and notes remain readable. An explicit new action can begin future tracking: a previously unrecorded stage stays unrecorded until Mark Pinning; a historically registered Fruiting record can record future harvests with unknown earlier dates. Missing spawning dates keep timing unknown.

The existing native FR `stage` field remains compatible (colonizing/ready/fruiting/finished). Additive `fruiting_stage` and `current_flush` fields project operational stages; the UI consistently uses this projection. New operational stage changes use the dated grow actions. Existing explicit terminal APIs synchronize the operational ending and label release; an old Finished patch without a date leaves completion timing unknown. Genetic genealogy, LC media defaults/volumes, agar Germinating/Ready/Used, spawn readiness, permanent IDs, acquisitions, recipe snapshots and archives remain intact.

## API

All mutations require a `request_key` and use the existing immutable command journal.

- `GET/POST /api/fruiting/environment`: optional singleton settings and expected revision.
- `POST /api/fruiting/create`: one `spawn_id`, `recipe_id`, `count`, `spawning_date`, optional `spawn_grams`, `substrate_grams`, `notes`, `material_type` and per-destination `label_choices`.
- `GET /api/fruiting` and `/api/fruiting/records/{FR}`: listings, snapshots, history and calculated results.
- `POST /api/fruiting/records/{FR}/stage`: `pinning`, `fruiting`, `next_flush`, `complete` or `failed`, with date/notes.
- `POST /api/fruiting/records/{FR}/harvests`: harvest data associated automatically with the current flush.
- `POST /api/fruiting/harvests/{HR}/edit`: full measurements/notes/date with expected revision; `GET .../history` exposes earlier revisions.
- `GET/POST /api/fruiting/harvests/{HR}/photos`: exact harvest images; existing library image/viewer/cover/removal URLs remain compatible.
- `POST /api/fruiting/records/{FR}/environment`: a meaningful dated environment change, optional settings and required notes.

## Validation

Run backend/frontend suites and the production build, then all existing browser smoke scripts plus:

```bash
.venv/bin/python scripts/fruiting_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/preparation_docker_smoke.py cultivatinator:milestone-2c3
```

The extended Docker script verifies earlier milestones alongside new grow/flush/harvest data, late dry weights, subjective potency, exact harvest photos, environment snapshots, idempotent retries and explicit release after container recreation. All tests use disposable local databases/volumes. The Debian installation is not accessed or deployed. Initial 2C.3 validation passed: **167 backend tests**, **106 frontend tests** across ten files, the production build, fresh/repeated Alembic upgrade/current/check at **0011_fruiting** with no schema drift, empty-history downgrade/re-upgrade, the populated 0010 upgrade regression, all five browser suites, and the local Docker build/recreation check. Browser coverage includes desktop/mobile layout, exact harvest photo uploads, multiple harvests/flushes, late dry weights, environment snapshots, totals/timing and label reuse. One existing upstream Starlette/AnyIO deprecation warning remains. Initial stale deferred-workflow assertions, fixture assumptions and browser-discovered route/accessibility issues were corrected; no final test/build failures remain.

### Photo enhancement validation

The enhancement adds regression coverage for optional/multiple Pinning photos, exact flush/grow ownership, Next Flush, later attachment/removal without date changes, existing harvest photos, populated 0011 upgrades, inline Harvest photos, partial upload failures, failed history refreshes and safe record/photo retries. The real-browser suite injects a photo-upload failure and verifies recovery without a duplicate harvest. Docker checks retain both flushes' Pinning images alongside harvest images across recreation. Final enhancement validation passed: **173 backend tests**, **115 frontend tests** across eleven files, the production build, fresh/repeated Alembic upgrade/current/check at **0012_pinning_photos** with no drift, empty downgrade/re-upgrade, populated 0011 upgrade with existing images, all five browser suites, and Docker build/recreation/photo persistence. One existing upstream Starlette/AnyIO deprecation warning remains. No final test or build failures remain.
