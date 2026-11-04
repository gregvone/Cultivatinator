# Milestone 2E — Dashboard Completion

The dashboard answers what needs attention, what is growing, and what happened recently, using existing recorded cultivation facts. It retains Quick Create, the industrial console layout and collapsible panels. Growing Conditions is hidden pending Environmental Monitoring; the environmental response field and existing observation data remain compatible. Recent Photographs remains deferred. No daily logging, predictions, sensors, external services or new containers are introduced.

## Attention rules

| Stable rule ID | Eligible records | Recorded date | Default |
| --- | --- | --- | --- |
| `ready` | Ready established agar; Ready spawn jars/bags | Ready date, if recorded | Always available |
| `fruiting_action` | FR with recorded Colonizing, Ready, Pinning, Fruiting or Harvest stage | Current stage date, if recorded | Review possible next action |
| `agar_growing` | Agar with Colonizing lifecycle (displayed Germinating) | Inoculation date | More than 21 days |
| `spawn_colonizing` | Colonizing spawn | Inoculation date | More than 28 days |
| `fruiting_colonizing` | Colonizing FR | Spawning date | More than 21 days |
| `pinning` | Pinning FR | Current flush's Pinning date | More than 14 days |
| `fruiting` | Fruiting FR | Current flush's Fruiting date | More than 14 days |
| `recent_failure` | Explicit Failed cultures/spawn/FR | Recorded failed date | Today and previous six calendar days |

Time reminders are customizable reminders, **not biological deadlines, diagnoses or predictions**. At exactly the threshold there is no elapsed-time reminder; it appears the following day. Missing, invalid or future dates do not create elapsed reminders. Administrative Active never makes agar Ready. Undated legacy records retain their unknown readiness; uninoculated prepared media and pending, unestablished spore cultures are not treated as established Ready agar. Undated failures are not assigned a historical failure date from registration time.

Archived, Used, Completed, Depleted and otherwise terminal records do not produce actionable reminders. Explicit recent failures appear only as Review / history, with no inferred cause, and stop appearing after seven calendar days. A FR stage produces a manual review suggestion (for example, mark Fruiting **when observed**), not a claim that it is biologically ready. Each record/rule pair occurs once; a stage review and its separate overdue reminder can both apply.

Every item links to its permanent record, shows its latest recorded physical label (including released labels), permanent ID, known strain/culture identity, category, severity, description and available date/elapsed days. Labels are never used as alert keys. FR identity uses the same batched provenance resolution as Reports: operational source, otherwise shared/specific allocations, or acquired line. Mixed and partially identified strains remain explicit.

## Snooze, dismissal and settings

Snooze hides a particular issue for 1, 3 or 7 periods of 24 hours, using an absolute UTC expiration. It returns after expiration if still applicable. Dismiss hides the issue until its relevant lifecycle changes. Its fingerprint includes the recorded lifecycle/stage, stage date, flush number and latest explicit lifecycle event ID. Notes, label edits, photographs, harvest measurement corrections, repeated reads and page refreshes do not reset a dismissal. A different flush is a new issue even if dates coincide. A resolved rule disappears automatically. Disabling a threshold does not discard an unchanged dismissal.

Use **Undo**, or **Review snoozed / dismissed alerts → Restore alert** to reverse a suppression. Only current, applicable suppressed items appear in that review. Open Alerts counts every current visible rule, including items beyond the first dashboard page. Its keyboard-accessible link expands and focuses Needs Attention. All Attention and hidden review pages show 25 results per page. Failed/stale mutations show an error; stale fingerprints return HTTP 409 instead of hiding a different issue.

**Settings → Attention Preferences** configures each of the five elapsed rules independently: enabled/disabled, integer 1–365 days. General cultivation authentication is not required. Saving preferences and dismissals changes no cultivation, label, photo, inventory, recipe, acquisition or ActivityEvent row.

Preferences and suppression state are stored atomically in **`/data/settings/dashboard.json`**, with a versioned, validated format. The existing one-worker runtime lease and mutation gate serialize writes; file replacement and directory metadata are fsynced. GETs do not create settings files. Storage is bounded to 5,000 suppression entries and a 2 MB read limit; resolved/changed states and expired snoozes are cleaned on alert mutations. A corrupt/unreadable settings file produces a visible HTTP 503, rather than silently forgetting dismissals. Repair or restore that specific file from a trusted backup while the app is stopped; do not replace the database to fix a dashboard preference.

**No Alembic migration, archive format change, dependency, Docker/Compose change or helper protocol change is needed.** The schema head remains `0013_journal_photos`. Existing workspace backups already include `settings/`, so preferences/dismissals survive container recreation and full restore with the corresponding cultivation dataset. Restoring an older backup without this file starts with default preferences and no dismissals. Stored archives, schedules/retention, administrator credentials, Trusted LAN checks, CSRF and restricted helper protections are unchanged.

## Activity, stages and harvests

Recent Activity shows the latest **15 persisted ActivityEvents**. `/activity` provides 25-item pages and filters for laboratory cultures, spawn, fruiting, spores, lines, strains and grow batches. Sorting uses actual timestamp descending, then permanent event ID descending to resolve ties. The UI renders the actual recording timestamp in the browser's local time, never a backdated cultivation date extracted from event descriptions. It links to archived records with an Archived indicator. Labels and identities reflect the current record; event descriptions/timestamps remain the persisted historical facts. No synthetic events are generated for dashboard settings or alert controls.

The stage overview separates Laboratory, Spawn and Fruiting container counts; each biological record belongs to one group/stage. Legacy records without a recorded stage contribute to active totals when applicable but not a fabricated stage bucket. In particular, the historical FR `ready` placeholder means Stage not recorded, matching existing FR details; it is not counted as biological Ready. Laboratory Colonizing agar is named Germinating on its detail/list. URL-driven filters are shareable and preserve back/forward navigation:

- `/laboratory?filter=active`, `filter=colonizing`, `filter=ready`
- `/cultivation?view=spawn&filter=active` (or `colonizing`, `ready`)
- `/cultivation?view=fruiting&fruiting=active` (or `colonizing`, `ready`, `pinning`, `fruiting`, `harvest`)

The three record cards open these active lists. The unfiltered Cultivation page continues to show both spawn and FR lists. Active Cultivation shows Ready first, then newest registered, deterministically, up to 24 records with a total and links to the full lists.

Recent Harvests covers **today plus the preceding 29 calendar days, inclusive**, using the browser's IANA timezone to determine today (API defaults to UTC). Future harvest dates and older dates are excluded. It counts current HarvestEntry rows, including historical/archived grows; HarvestRevision snapshots are never summed. Wet weights are summed as integer milligrams and converted with Decimal. Recorded zero is a known measurement. Missing weights remain unknown, the known-measurement count is explicit, and an entirely unmeasured/empty period has no wet-weight total. The period boundaries/timezone and Reports link are displayed.

Dashboard data refreshes on mount/return, browser focus/visibility return and successful alert actions. Background refresh preserves mounted panel/Undo state. It does not poll continuously or push changes between devices. Summary payloads cap alerts at 25, active records at 24, activity at 15; counts cover the entire eligible dataset. Query count is fixed rather than one query per record, with bounded activity owner lookups and consolidated source/label/lifecycle joins. Deriving rule eligibility scales with the active dataset; large installations may eventually benefit from database-side candidate pagination.

## Validation and acceptance

Automated coverage is in `backend/tests/test_dashboard.py`, `frontend/src/Dashboard.test.tsx`, `scripts/dashboard_browser_smoke.py`, and the extended existing `scripts/backup_docker_smoke.py`.

Acceptance covers eligibility and terminal/archived exclusions; missing/future dates and threshold boundaries; recent failures; actual counts; snooze expiration and persisted reload; Undo/Restore; dismissal stability across unrelated events and disabled preferences; new lifecycle/flush reactivation; stage links; actual activity timestamps, deterministic ties, microsecond precision, equivalent UTC offsets, archive links and paging; current corrected harvest values, missing wet coverage, date/timezone boundaries; bounded results/query count; settings validation/corruption; unchanged schema and settings backup round trips. Chromium checks the real API/UI, empty/error/retry states, keyboard focus, filters, preferences, and 390 px mobile layout without horizontal overflow. Docker acceptance checks dashboard settings/dismissals after restart and restore, existing photos, ownership, writer fencing, startup-failure rollback and interrupted recovery.

Run from the repository root, with optional Playwright and Chromium installed separately for smoke tests:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/dashboard_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/reports_browser_smoke.py /usr/bin/chromium
docker build -t cultivatinator:milestone-2e .
.venv/bin/python scripts/backup_docker_smoke.py cultivatinator:milestone-2e
CULTIVATINATOR_TEST_IMAGE=cultivatinator:milestone-2e .venv/bin/python scripts/backup_browser_restore_smoke.py /usr/bin/chromium
CULTIVATINATOR_TEST_IMAGE=cultivatinator:milestone-2e CULTIVATINATOR_TEST_BACKUP_AUTH_MODE=trusted_lan .venv/bin/python scripts/backup_browser_restore_smoke.py /usr/bin/chromium
```

Validation result: **304 backend tests and 183 frontend tests passed**, along with the production frontend and Docker builds. Fresh/repeated Alembic upgrades and schema drift checks passed at `0013_journal_photos`. Dashboard, Quick Create and Reports Chromium suites passed; complete browser restore suites passed in both password and Trusted LAN modes. The extended host-CLI Docker suite passed preference/dismissal restart and restore persistence, photograph/history retention, rollback and interrupted recovery. No outstanding test failures; one existing Starlette/AnyIO deprecation warning remains.

All smoke tests use disposable local datasets and projects; none target Debian. Optional managed build CA secrets may be passed as documented in Dockerfile; do not disable TLS verification. Debian functional acceptance remains a separate user action.

## Exact Debian review update (not performed by this task)

Use the existing checkout and Dockge stack; do not create another instance, overwrite `.env`/Compose, copy databases, reset labels or reset credentials. First create/verify/download a backup through Settings, finish any restore/backup, and check that Git has no local source edits that would be overwritten. For the requested review branch:

```bash
cd /storage/tv/cultivatinator
sudo git status --short
sudo git fetch origin
sudo git switch feature/milestone-2e-dashboard
sudo git pull --ff-only origin feature/milestone-2e-dashboard
sudo docker compose --project-directory /opt/stacks/cultivatinator --env-file /opt/stacks/cultivatinator/.env -f /opt/stacks/cultivatinator/compose.yaml config --quiet
```

If local source edits exist, preserve/reconcile them before switching; never use `git reset --hard` or `git clean` on the co-located installation. No environment changes are needed: retain `APP_PORT=8085`, `DATA_DIR=/storage/tv/cultivatinator`, your existing maintenance directory and `trusted_lan` / `192.168.68.0/24` settings. Keep the helper targeting `/opt/stacks/cultivatinator/compose.yaml`; this dashboard-only change does **not** require reinstalling or resetting it.

In Dockge, open the **existing cultivatinator** stack and choose **Build & Start / Deploy** with a local rebuild. A registry Pull alone will not rebuild the checkout. Alternatively, use this equivalent host command on that same project (choose one management path):

```bash
sudo docker compose --project-directory /opt/stacks/cultivatinator --env-file /opt/stacks/cultivatinator/.env -f /opt/stacks/cultivatinator/compose.yaml up -d --build --wait app
sudo docker compose --project-directory /opt/stacks/cultivatinator --env-file /opt/stacks/cultivatinator/.env -f /opt/stacks/cultivatinator/compose.yaml ps
curl --fail http://127.0.0.1:8085/api/health
sudo systemctl status cultivatinator-maintenance.service --no-pager
```

For an installation still managed by the root Compose file, keep using that existing management path and the same data bind; see [Dockge migration](DOCKGE.md) before changing ownership of deployment management. Never start both definitions as separate projects.

Open `http://SERVER-IP:8085`, verify existing cultivation records/photos, then check Ready alerts, snooze/refresh/Undo, stage-filter links, local activity times and 30-day harvest coverage. Change one reminder setting, recreate/restart the same container, and confirm persistence. Verify Backup & Restore still opens for the authorized LAN without a password and can create/verify a new archive. Do not perform a destructive restore solely as dashboard acceptance on the live dataset. No automatic merge or Debian deployment is authorized by this implementation.


## Implementation map

| Area | Changed files |
| --- | --- |
| Backend projections and API | `backend/app/dashboard.py`, `dashboard_store.py`, `api/routes.py`, `main.py`, `schemas.py`, `reports.py` |
| Backend regression coverage | `backend/tests/test_dashboard.py` |
| Frontend pages | `frontend/src/pages/Dashboard.tsx`, `DashboardHistory.tsx`, `Growing.tsx`, `Fruiting.tsx`, `Settings.tsx` |
| Frontend components/data/routes/style | `frontend/src/components/DashboardRecords.tsx`, `DashboardPreferences.tsx`; `frontend/src/App.tsx`, `api.ts`, `dashboardApi.ts`, `useApi.ts`, `styles.css` |
| Frontend regression coverage | `frontend/src/Dashboard.test.tsx`, `App.test.tsx` |
| Smoke coverage | `scripts/dashboard_browser_smoke.py`, `scripts/backup_docker_smoke.py` |
| Documentation | `README.md`, `docs/ROADMAP.md`, `docs/MILESTONE_2E.md` |
