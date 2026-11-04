# Milestone 2G — Fruiting Tent Environmental Monitoring

Implemented on `feature/milestone-2g-environment`, awaiting review. No merge or Debian deployment is performed. Monitoring is manual and optional. There are no seeded tents, profiles, targets or readings, and no daily schedule, missed-reading alerts, device connection, CSV import, automation or cloud dependency.

## Architecture and data

The existing SQLite/FastAPI/React application and mutation gate remain in place. `environment.py` is the ingestion boundary for a future explicitly implemented source adapter. All mutations use the existing `Command.request_key`, serialized `BEGIN IMMEDIATE`, InventoryOperation fingerprint/replay, revision conflict and transaction conventions. New EP/ET IDs use the existing allocator. `source=manual` distinguishes observations from legacy `FruitingEnvironment` / `FruitingEnvironmentChange` configuration snapshots, which are untouched. No cultivation, lineage, status, physical-source, label or harvest mutation is performed by monitoring.

Additive Alembic revision **0014_environment_monitoring**, after confirmed head **0013_journal_photos**, adds eight tables:

- `environmental_profiles`: named, revisioned user targets, optional species label/notes and archive state. Bounds may be blank; one-sided bounds are supported. Profile targets and historical snapshots are JSON documents, with typed finite numeric validation at the API boundary.
- `fruiting_tents`: permanent identity, description, archive state, revision and selected profile FK.
- `environment_profile_assignments`: immutable dated assignments and profile revisions, including target/name snapshots. Editing a selected profile appends its revision for each assigned tent, effective at edit time.
- `environmental_readings`: observation and creation timestamps, source, actual required °F/RH values, optional ppm CO₂ and controller levels, notes, original profile/limits and per-metric evaluations. Corrections reference their original via a unique FK.
- `tent_occupancies`: real fruiting-container and tent FKs, entry/removal timestamps and revision. Database triggers independently prevent overlapping intervals across all tents, including direct SQL insert/update. Exact adjacent intervals are allowed.
- `environment_audits`: immutable before/after snapshots, operation reference, recording time and correction reason for descriptive edits and occupancy changes.
- `environment_warnings`: a small current projection keyed by tent/metric, referring to its decisive reading.
- `environment_warning_events`: immutable before/after states and operation/time history, including correction-induced transitions and resolution.

Foreign keys, reading value/level checks, positive revisions and history indexes accompany these tables. SQLite triggers forbid updating/deleting readings, assignment snapshots, audits and warning events. No old migration or cultivation table is altered. Downgrade refuses when any environmental record exists; it does not discard monitoring history.

## Time, targets and corrections

All stored observation/occupancy/assignment timestamps are canonical UTC ISO-8601 strings with six fractional digits and `+00:00`, making indexed lexical order chronological. APIs require timezone-aware timestamps. Browser inputs default to the current local instant and submit an explicit UTC instant. Local display uses browser timezone, including historical DST offsets. Nonexistent local DST times are rejected; during an ambiguous repeated hour, the browser chooses the earlier occurrence. API clients can explicitly supply either offset. Readings/occupancy reject dates before 1900 or over five minutes in the future; creation time is separate and cannot be supplied by the user.

A new observation uses the latest assignment/revision whose effective time is at or before its observation time. A backdated observation before any assignment has no profile. Editing a profile never changes earlier snapshots. Temperature bounds accept −148–212 °F, RH 0–100%, CO₂ 0–1,000,000 ppm: these are input validity bounds, not cultivation recommendations. User targets require min ≤ max; unset bounds stay unset. Optional controller levels are whole numbers 0–10, labeled as manually entered controller levels rather than verified device telemetry.

Corrections append a complete replacement observation plus a required reason. The original remains readable with a replacement link, original evaluations and original creation time. A correction **retains its original profile/target snapshot**, even when its observation time is corrected. This makes the comparison basis explicit and stable. Correct the current replacement to correct again; branching correction chains are rejected. Current warning state is reconstructed from effective, nonsuperseded observations; old evaluations and transition audit are never rewritten.

## Warning rules and Dashboard

Each metric is independent. Missing CO₂ is unknown. A missing target or value is not an evaluation and cannot resolve a warning. Bounds are inclusive; outside values evaluate `low`/`high`, inside values `normal`. Current state uses the latest applicable, nonsuperseded observation ordered by `(observed_at, integer reading ID)`; the greater ID wins an equal-time tie. Backdated observations retain their evaluations but cannot override a newer applicable observation. Corrections append an audit transition if they change the decisive observation/state.

Warnings persist across refresh/restart, silence and profile changes. A newer applicable in-range observation resolves that metric; a profile change without a reading does nothing. Archived tents retain their unresolved warnings and history, and must be restored to enter new readings. There is no hide, dismiss, snooze or fabricated recovery. Dashboard counts, initial attention and 25-item all-attention pages share the existing candidate projection and link directly to the tent. Display shows the latest abnormal **recorded** value and observation time, never a live condition.

## Occupancy and UI

Environment is a primary navigation item with URL tent selection and normal browser history. Users can create Boom Room 2 or any other name, edit/archive tents, create blank profiles, explicitly select one shared profile, add readings, inspect charts/table/reading details, correct readings and edit occupancy with a reason/revision check. Mixed species retain their own identities and use one user-selected tent profile; no biological suitability is inferred.

Occupancy periods are `[entered_at, left_at)`. An open removal means still assigned. Entry/removal changes are audited; tent/container identity is permanent within an interval, so a move uses a new interval. Container lifecycle changes do not automatically close occupancy. A fruiting detail has an expandable occupancy and conditions panel plus a management link. Queries correlate readings to exact occupancy instants; they never infer continuous exposure. Unassigned legacy records are valid and show empty history.

Charts show only recorded points, without connecting/interpolating them. Each observation's two-sided historical target range has its own vertical target bar. One-sided targets remain explicit in the table/details. Local-time axes and a complete accessible table cover °F, RH and available CO₂. Presets cover 24 hours, 7 days, 30 days, plus custom local ranges. Charts cover the displayed page only; the UI explains this bound. No historical data is loaded on dashboard visits beyond current warning references. Tent overview queries latest values independently, so an omitted CO₂ does not erase the most recent actual CO₂ value/time. Old readings show their timestamp and age without inventing staleness alerts.

Responsive panels use the existing shell/theme and native keyboard forms. Dropdowns explicitly set dark background/light text. Requests expose loading, retry and validation errors; submissions retain an idempotency key for retrying identical payloads. Fruit-detail history loads only when expanded. No application runtime dependency is added; Playwright and formatters are optional development tools only.

## API contracts

All paths below are under `/api/environment`. POST/PUT bodies require a fresh `request_key` (8–100 characters); retry the same key/body for the same committed response. Revisioned edits require `expected_revision`; stale edits return 409. Invalid values return 422; missing records return 404.

| Route | Contract |
| --- | --- |
| GET/POST `/tents` | List or create `{name, description?, status?}` |
| PUT `/tents/{id}` | Same fields plus expected revision |
| GET/POST `/profiles` | List or create `{name, species?, notes?, status?, targets?}`; target keys are `temperature_f_min/max`, `humidity_min/max`, `co2_min/max` |
| PUT `/profiles/{id}` | Same fields plus expected revision; append effective snapshots for assigned tents |
| POST `/tents/{id}/profile` | `{profile_id: string or null, expected_revision}` |
| GET `/tents/{id}/overview` | Tent, selected profile, independently timestamped latest metrics, open warnings and current occupancy count |
| POST `/tents/{id}/readings` | `{observed_at, temperature_f, humidity, co2?, humidifier?, fan?, notes?}` |
| POST `/tents/{id}/readings/{reading}/correct` | Complete reading fields plus nonempty `reason` |
| GET `/tents/{id}/readings` | Aware `start/end`, `page`, `page_size` (default 100, max 500); includes original/replaced readings, snapshots, evaluations and exact occupants |
| GET `/tents/{id}/history` | Warning event pages of 50, plus latest 100 immutable assignment snapshots |
| GET `/containers` | Search permanent ID with `q`, 50 choices/page, derived existing strain/label identity |
| GET `/occupancy` | Filter by `tent_id` and/or `fruiting_id`, 50/page |
| POST `/tents/{id}/occupancy` | `{fruiting_id, entered_at, left_at?}` |
| PUT `/tents/{id}/occupancy/{interval}` | Same identity, updated dates, expected revision and required reason |
| GET `/containers/{id}/readings` | Effective readings taken within exact occupancy periods, 50/page |
| GET `/audit/{entity_type}/{entity_id}` | Before/after revision audit, 50/page; e.g. `tent_occupancies/1` |

History payloads return `{items,total,page,page_size}`. Tent/profile lists are configuration catalogs intended for a personal installation, not sensor-scale histories. Warning queries use current projection rows; reading/occupancy/history endpoints are bounded and indexed. Additional source adapters can later reuse validation, canonical ordering, snapshot evaluation and operation idempotency; CSV import, sensors, device discovery, fan control and deduplication beyond request replay remain deferred.

## Backup, review deployment and rollback

Ordinary SQLite backups include all new tables, audits and snapshots. Archive format, checksums, photo checks, exact schema/revision checks, mutation fencing, privileged helper permissions and writer safety are unchanged. `backup_schema.json` gains exactly the new tables/indexes/triggers. Backend tests verify checksummed extraction and app startup against an isolated restored archive.

**Schema compatibility is exact.** A 0014 archive cannot be restored using 0013 application/helper code. Likewise, a 0013 archive requires its matching code/helper to validate/restore, followed by the normal app upgrade if moving forward. Checking out older Git code alone is not a database rollback. The installed privileged helper keeps a separate copy of the migrations and schema catalog: an existing 0013 helper will safely reject 0014 backups/restores. Before approving Debian rollout, arrange a separately reviewed matching helper code-bundle update using the existing maintenance procedure, preserving its configuration, credentials, permissions and fencing. This task does not install or reconfigure it. Do not weaken the revision/schema check to work around a mismatch.

User-operated review procedure (not executed here):

1. Review the branch/PR and migration. Confirm both app and helper compatibility for the intended revision. Preserve existing source edits, Dockge/Compose configuration, `.env`, maintenance credentials and ownership. Never run a second app against the same data directory.
2. On the existing 0013 deployment, create, verify and download a complete backup through Settings. Keep matching old code and helper available for recovery. Stop if the backup is not recoverable.
3. In the existing checkout, `git fetch origin`, `git switch feature/milestone-2g-environment`, and `git pull --ff-only origin feature/milestone-2g-environment`. Do not reset/clean the co-located data/source root.
4. After compatibility review, rebuild the **existing** Dockge stack, or use its existing Compose project, env file and data bind. Startup runs additive Alembic 0014 before serving; failure stops startup. Keep port 8085, UID/GID 10001 and the same persistent data path. No new service or environment setting is required.
5. Check `/api/health`, legacy cultivation/genetics/photos/harvests, create a blank profile and a tent, enter a real observation, verify warning recovery and occupancy on desktop/mobile. Create and verify a new 0014 backup and complete an isolated matching-helper restore acceptance before relying on production restore.
6. If rollback is needed, stop writers and use the established verified restore procedure with a matching pre-upgrade backup, matching application/helper revision and writer fencing. Restore only the four data children, preserving Git/source/Compose/`.env`, backup catalog and credentials. Never copy a live SQLite file or drop new tables to force a downgrade. Retain any new monitoring data separately before returning to a pre-monitoring backup.

No production data, Debian server or privileged helper is touched by the implementation/test work. Privileged restore acceptance may fail in managed hosts whose `/proc` writer inspection is restricted; that remains a blocked check, not permission to bypass fencing.

## Verification

From repository root:

```sh
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test -- --maxWorkers=1 --testTimeout=15000 && npm run build)
.venv/bin/python scripts/environment_browser_smoke.py
.venv/bin/python scripts/genetics_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/dashboard_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/fruiting_browser_smoke.py /usr/bin/chromium
docker build -t cultivatinator:milestone-2g .
.venv/bin/python scripts/backup_docker_smoke.py cultivatinator:milestone-2g
```

Use the Dockerfile's existing optional `proxy_ca` secret for managed proxy builds; keep TLS verification enabled. All tests use disposable datasets. Final results are recorded below after verification.


Validation results: the initial complete backend run passed **340 tests**. After the final strict numeric and expanded backup cases, the full regression rerun passed **342 tests**. The final Environment suite passed **29 tests**, including three additional raw nonfinite-JSON cases. All **191 frontend tests** passed using one worker and a 15-second test timeout; the existing 600-node Genetics interaction test exceeded its default five-second timeout under concurrent browser/Docker load, then passed with those resource-appropriate CLI settings. No repository test timeout or assertion was weakened.

The production frontend build and final production Docker build passed. The final image is `cultivatinator:milestone-2g`, digest `sha256:aa79b0da20588dadcc6264169f8e07d7ce5d949ebe06a81efef508529f5fa82f`. A repeated build initially exhausted the managed VFS disk; removing disposable build cache allowed the final build to complete. Frontend bundling reports a nonblocking ~501 kB chunk warning; one existing Starlette/AnyIO deprecation warning remains.

Chromium Environment acceptance passed: empty state, creating a tent, manual entry and optional fields, original target snapshots, correction traceability, persistent Dashboard warning/navigation, newer in-range resolution, charts and table, custom date ranges, explicit container assignment and recorded conditions on the existing fruiting detail, native dropdown colors/labels, keyboard, reduced motion and mobile overflow. Existing **Genetics/Magic Kingdom**, **Dashboard**, and **Fruiting** browser suites also passed. Fresh/repeated migration, upgrade preserving legacy FR identity, Alembic/model drift and isolated backup extraction/restart tests passed; the final backup case retains profile/assignment, original and corrected readings, warnings, occupancy and audit history.

The privileged Docker backup acceptance verified a format-1 **0014 archive with ten checksummed files**, SQLite integrity/FKs and photo references. Its injected startup-failure rollback then failed closed because this managed host denies `/proc/1/fd/0` inspection. **Full privileged rollback/restore/browser-restore acceptance is not passed** and remains for a suitable isolated host before Debian rollout. Writer fencing was not weakened, and the installed helper was not modified. No merge, deployment or production data access occurred.
