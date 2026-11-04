# Milestone 2H — Grow Experimentation & Optimization

Current development: [2H.2 enrollment, creation and automatic lineage](MILESTONE_2H2.md).
The 2H.1 scope/verification below records the reviewed foundation; 2H.2 adds schema
0016 and requires a matching helper bundle before release.

## 2H.1 — Experiment foundation

Implemented for review on `feature/milestone-2h-experiments`, based on verified main
`a625abb33c52bdb99ecc775dc872910dc827438f` (merged 2G). No deployment, production
helper update or merge is performed. Migration head was verified as
`0014_environment_monitoring` before adding `0015_grow_experiments`.

### Workflow and boundaries

Experiments supports a three-step setup: question/outcome, groups, review/save.
Substrate, Genetics and Growing conditions are all available. Scope is explicitly
Fruiting; agar, LC and spawn experimentation is not operational. One primary
variable, one primary outcome, two or more named treatment groups and an optional
single control are required. Hypotheses, secondary outcomes, allocation schedule,
blocking, eligibility, exclusions, observation window and coverage expectations
are optional. Advanced settings document intent; they do not run analyses or
require routine environmental logging.

Save Draft preserves a snapshot. Commit Plan moves Draft to Planned and records
the first committed plan. Start Experiment records the actual treatment start,
separate from the server-recorded start command time. Running can become Completed;
Draft/Planned/Running can become Cancelled. Archive/Restore preserves lifecycle
state and history. Cancelled/Completed plans cannot be edited. There is no delete
or reopening command. Every transition needs a reason/current revision. Category
is permanent; a materially different category needs a separate experiment.

Plans can be revised while Draft, Planned or Running. Original snapshots are
never overwritten, removed groups keep their permanent identities, and post-start
amendments are labeled. Amendments never recalculate the frozen start classification.
Users can expand every historical plan and before/after audit, with paginated
history. Lifecycle actions never finish grows, consume spawn, release labels,
change tent occupancy or rewrite harvests.

### Scientific timing

Classification concerns **treatment-specific plan/allocation timing**, not an
experiment's creation date, first harvest or a claim of causal validity.

- Prospective requires the relevant committed plan and concrete treatment-unit
  allocations to precede the actual treatment instant. Unit evidence must refer
  to that plan revision. Both allocation time and actual recording time are used;
  a backdated allocation cannot manufacture earlier evidence.
- A known commitment after treatment is Retrospective, including ongoing grows.
- Missing concrete allocation evidence or equal-time ordering is Uncertain.
- Date-only starts remain Uncertain unless the commitment is demonstrably after
  every possible instant on that date across UTC offsets (then Retrospective).
- Future actual starts are rejected: leave a future treatment Planned.

**2H.1 does not expose concrete unit allocation/enrollment workflows.** Consequently,
a newly planned experiment cannot obtain a Prospective label just by typing an
allocation schedule. It remains Uncertain unless timing proves Retrospective.
The classifier's Prospective path is tested with concrete relational allocations
seeded in disposable tests, ready for 2H.2/2H.3. This intentionally prevents a
foundation-only interface from making unsupported scientific claims.

### Relational model

Seven additive tables retain the existing biological/production database:

- `experiments`: category, fruiting scope, lifecycle, archive flag, revision,
  actual start timing, frozen classification and start plan revision.
- `experiment_plan_revisions`: immutable typed JSON snapshots, server commitment
  and recording times, operation FK and reason. Allocation commitment is reserved
  and nullable; free text does not populate it.
- `experiment_groups`: permanent experiment-owned identities; names/treatments/
  control designation are versioned within plan snapshots.
- `experiment_units`: independently assigned treatment unit, with one typed FK
  target (container, grow batch or tent trial), plan revision, allocation/recording
  times and block. Units are distinct from genetic sources and observations.
- `experiment_trials`: experiment/group/tent FKs, bounded treatment period and
  snapshot, reserved for environmental workflows.
- `experiment_memberships`: FR-to-unit association with exposure intervals and
  evidence. A container can have multiple sequential exposures and participate
  in multiple experiments. No yield or harvest copy is stored here.
- `experiment_audits`: immutable before/after command snapshots and reasons.

Composite FKs prevent cross-experiment groups/units/trials; a unit's trial must
also belong to its group. Unique unit targets prevent counting one container,
batch or trial repeatedly within an experiment. Sequential tent treatments use
separate trials/units. Memberships are observations of those units, not new
independent trials. Multiple flushes never create units. No outcome attribution
logic or duplicate harvest allocation is implemented.

Checks constrain types, state, revisions, ownership targets and ordered intervals.
Database triggers reject UPDATE/DELETE on plan revisions, audits and group
identities. Downgrade refuses if any experiment data exists. No historical
cultivation membership is inferred or backfilled.

### API

All paths are under `/api/experiments`; commands reuse `Command.request_key`,
`InventoryOperation` request fingerprint/replay, the full-request mutation gate
and serialized SQLite transactions. Same key/body replays the original response;
a different payload under that key or stale `expected_revision` returns 409.
Invalid bodies return 422; unknown IDs return 404. Typed response contracts are
included in OpenAPI.

| Method/path | Contract |
| --- | --- |
| GET/POST `/` (without trailing slash) | Paginated catalog / `{plan, request_key}` draft creation |
| GET `/{id}` | Current plan, lifecycle, revision, timing and amendment flag |
| POST `/{id}/plan-revisions` | `{plan, expected_revision, reason, request_key}` |
| POST `/{id}/actions` | `{action, expected_revision, reason, request_key}`; start additionally requires exactly one aware `treatment_start` or `treatment_date` |
| GET `/{id}/history?page=N` | Plan/audit pages, separate totals, 50 each |

Plan outcomes are completed wet/dry yield, days to pinning/first harvest, completed
cycle days and terminal failure rate. These are definitions only; calculations
and record eligibility arrive later. Existing Reports remains unchanged.

### Backup, release blockers and rollback

`backup_schema.json` includes the exact seven tables, constraints, indexes and
history triggers. Existing ZIP format, photo verification, write fencing,
credentials, persistent directories and Docker architecture remain unchanged.

**Release blockers:** install a separately reviewed matching 0015 privileged helper
bundle and pass isolated privileged restore/rollback/interrupted-recovery acceptance
on a suitable host before any Debian rollout. Neither is performed by 2H.1.
The 2G `/proc` writer-inspection limitation remains unresolved historical evidence;
it is not permission to weaken writer fencing or to claim privileged tests passed.

Migration/schema compatibility remains exact: 0015 archives require matching 0015
app/helper code. A 0014 archive needs matching 0014 code/helper for restoration,
then an ordinary reviewed upgrade. The installed helper owns its separate schema
and migrations; updating the application alone does not update it. Preserve the
old matched release and verified external backup before upgrading.

Rollback means stopped writers, a verified pre-upgrade backup and matching old
app/helper code. Never drop tables or run an older image against a newer database.
Restore only database/photos/files/settings, preserving co-located source, Compose,
.env, backup catalog and maintenance credentials. Preserve new-schema data before
rolling back where possible; a pre-upgrade restore loses later cultivation changes.
Port 8085, UID/GID 10001 and the single existing persistent mount remain unchanged.

### Deferred phases

- **2H.2:** real enrollment, provenance resolution, shared-source review, and
  atomic experiment-driven fruiting creation with destination-specific recipes.
- **2H.3:** concurrent/sequential trials, reviewed occupancy/profile suggestions,
  corrections, environmental coverage and crossover attribution.
- **2H.4:** shared Reports analysis and automatic observational Grow Insights.
- **2H.5:** broader browser/recovery/release acceptance. Deployment/merge requires
  subsequent review; no sensors or device control belong in this milestone.

### Verification

Final verification: **370 backend tests passed**, including **25 new experiment
cases**; **198 frontend tests passed**, including **6 new experiment cases**.
The production TypeScript/Vite build passed. The optional real Chromium experiment
acceptance passed: guided setup, three groups/advanced settings, commitment,
retrospective start, post-start amendment/original history, completion/archive/
restore, mobile overflow and reduced motion. Browser acceptance caught and fixed
collection trailing-slash handling; its regression is included in the backend suite.

Backend coverage includes fresh/repeated migration, preserved 0014 observations,
model drift, exact schema catalog and isolated backup verification/extraction.
Existing cultivation, genetics, Environment, Reports and backup regressions passed.
The suite reports one existing Starlette/AnyIO deprecation warning; Vite reports a
nonblocking roughly 514 kB JavaScript chunk warning. Formatters and Playwright
were installed only as temporary development tools; runtime dependencies and
lockfiles were not changed.

Reproduce from the repository root:

```sh
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test -- --maxWorkers=1 --testTimeout=15000 && npm run build)
# Optional development dependencies: Python Playwright and installed Chromium.
.venv/bin/python scripts/experiments_browser_smoke.py /usr/bin/chromium
```

This managed executor needs local socket/network permission for AnyIO TestClient;
a minimal portal reproduction established this before the final test runs. No
application workaround or test assertion was weakened.

**Not performed:** production Docker deployment/build acceptance, production helper
update, or isolated privileged 0015 restore/rollback acceptance. These remain
release work, including the historical 2G writer-inspection limitation. All tests
used disposable native data; no production data or Debian service was accessed.
