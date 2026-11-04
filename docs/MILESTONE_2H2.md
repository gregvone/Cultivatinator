# Milestone 2H.2 — Fruiting enrollment, creation and automatic lineage

Implemented for review on the existing `feature/milestone-2h-experiments` branch
and PR #14, continuing reviewed 2H.1 commit
`ef3a7532b2031f9ff9a34d81cacce713066753f8`. No deployment, production data mutation,
helper installation or merge is performed.

## Workflow

Commit an experiment plan, then use **Participants and groups**:

- Link an existing permanent FR to a group. The displayed source fingerprint and
  current experiment revision must still match at confirmation.
- Create new containers: choose one Ready spawn source and per-group substrate
  recipes/counts; save the concrete assignments, then create all destinations.
  Counts can be zero for groups not included in that operation. One genetics
  source may populate only one genetics group per operation; use separate sources
  for the other groups.
- Optionally confirm a source rule to associate downstream fruiting records from
  a spawn source, physical culture or exact culture line.
- Inspect permanent FR links, original plan group, current recorded sources,
  timing classifications, shared-source counts, assigned units and flush counts.
- Review a changed/conflicting assignment: keep its confirmed group, exclude it,
  or explicitly correct its group. Reasons and before/after evidence are retained.

Enrollment is available in unarchived Planned/Running experiments. Completed and
Cancelled experiments can still receive audited participation reviews without
reopening their lifecycle. Restore an archived experiment before reviewing it.
Source corrections flag historical assignments even in completed/archived plans;
automatic new enrollment occurs only in unarchived Planned/Running experiments.

Conditions participation requires an existing shared tent-trial unit rather than
inventing an independent unit for each container. Creating/scheduling those trials,
tent occupancy-based attribution and environmental coverage remain **2H.3**. The
UI explains this boundary. Substrate and genetics fruiting workflows are operational;
no agar/LC/spawn-stage experiment setup is introduced.

## Scientific timing and units

Individual memberships store the relevant plan revision, original classification,
actual treatment timing/precision, allocation evidence, origin and provenance
fingerprint. The experiment's frozen **plan start classification** remains a
separate historical summary. Participants can contain mixed classifications.

A known treatment instant is Prospective only when both the relevant plan and its
concrete allocation were committed earlier. The two-command creation workflow
provides a genuine earlier allocation record; creating and assigning containers
in one transaction alone would not prove earlier commitment. Treatments known to have begun before the plan or allocation commitment
are Retrospective. Missing/ambiguous ordering
remains Uncertain. Date-only cultivation records retain their limited precision;
no treatment instant is invented. A supplied instant must be compatible with the
recorded calendar day across possible UTC offsets and cannot be in the future.

Manual enrollment records allocation now unless it legitimately references an
existing shared unit's allocation evidence. Source rules preserve their actual
server recording time. Group corrections record new allocation time and cannot
promote a retrospective membership to prospective. Original evidence remains in
immutable enrollment events. Free-text schedules are never concrete allocations.

Container units must reference their own FR. Existing batch/shared-trial units may
cover multiple containers. Historical plan membership is enforced in application
validation and database triggers. Multiple flushes remain repeated observations;
no unit is created by adding a flush or harvest. Assigned-unit counts are not
claims of statistical independence: common spawn sources remain explicit, and
there are no inferential statistics or outcome rankings in this phase.

Existing membership exposure intervals are retained for future sequential trials.
No harvest is copied, apportioned or credited to several groups by 2H.2. Containers
can participate in several experiments without duplicating production records.

## Provenance and automatic association

The resolver reuses Reports' operational/shared/specific/acquired source semantics.
It follows actual `PreparedMaterial`/`MaterialTransfer` relationships upstream
through physical cultures, with cycle/depth protection. Exact culture-line identity
is distinct from genetic parenthood: possible parents do not become material
transfers or inherited group assignments. Possible ancestry prevents automatic
pure-genetics attribution. Archived biological records remain resolvable.

Every contributing source path must resolve completely to one compatible group
under confirmed rules for the applicable plan. Mixed genetic lines, missing paths,
unknown ancestry and contradictory groups become review candidates. New ordinary
cultivation operations automatically associate unambiguous fruiting descendants.
Registering a rule also examines existing records, with retrospective/uncertain
classification where appropriate.

Reconciliation runs in the existing domain transaction, including legacy provenance
corrections. It preserves confirmed groups, marks changed provenance/rules for
review, appends history and increments the affected experiment revision. Explicit
Keep acknowledges the reviewed rule conflict until further evidence changes; an
unrelated cultivation save does not immediately undo that decision. Reads never
create associations. Request replay never reruns reconciliation.

## Atomic fruiting creation

`fruiting.create_fruiting` is a transaction-level service shared by the existing
`POST /api/fruiting/create` command and experiment creation. No HTTP endpoint calls
another HTTP endpoint.

The ordinary command retains its payload/fingerprint, one-recipe semantics, exact
replay and whole-source consumption. The shared service validates every destination,
freezes all recipe snapshots before any destination is written, creates batch/FR/
source/label/run/flush records, and consumes/releases the spawn source once.
Experiment membership creation is in that same transaction. Any failure, including
late membership/timing validation, rolls back destinations, labels, memberships,
source consumption and operation results together. Lost responses replay exactly.

Saved creation assignments pin the plan and recipe revisions. Changed plans or
recipes require new review/assignments; unavailable spawn fails safely at creation.
The allocation itself does not reserve/consume material or promise availability.

## Additive schema and API

Migration **0016_experiment_enrollment** follows **0015_grow_experiments**, which is
unchanged. A further revision is necessary to persist actual pre-treatment creation
assignments, confirmed source rules and independent enrollment audit events; these
were not represented by 0015's placeholder associations. Events support several
experiments/memberships affected by one ordinary provenance operation.

Three new tables:

- `experiment_creation_allocations`: immutable source, historical plan FK,
  destination groups/recipe revisions, server recording time and operation FK.
- `experiment_source_rules`: typed spawn/physical/line FKs, plan/group FKs, server
  recording time and active state. Stopping a rule is audited and retains its rows.
- `experiment_enrollment_events`: append-only before/after membership/rule/allocation
  snapshots, reasons, time and optional existing operation FK (legacy provenance
  commands have their own audit without an InventoryOperation).

Additional triggers prevent wrong-FR container unit memberships and group/unit/rule
assignments outside the applicable historical plan. New history tables reject
UPDATE/DELETE. Downgrade refuses to discard enrollment history. No production table
is rewritten or new biological record type introduced. `backup_schema.json` includes
the exact new tables/indexes/triggers.

All paths below begin `/api/experiments/{id}`. Mutations use existing request keys,
serialized transactions and current `expected_revision`; stale state/evidence
returns 409, invalid values/ownership 422, and absent records 404. Response contracts
for participants, membership results and creation are included in OpenAPI.

| Route | Purpose |
| --- | --- |
| GET `/participants?page=N&q=FR-ID` | Paginated participants/candidates, source rules, classifications and separate unit/source/container counts |
| POST `/enroll` | FR, historical plan/group, source fingerprint, optional known treatment time/date or existing shared unit |
| POST `/source-rules` | Confirm a source-to-group association |
| POST `/source-rules/{rule}/stop` | Stop future automatic linking and review affected confirmations |
| POST `/creation-allocations` | Commit source and destination group/recipe/count assignments |
| POST `/fruiting` | Consume a saved allocation and atomically create fruiting records/memberships |
| POST `/participants/{membership}/review` | Keep/exclude/reassign using current fingerprint and required reason |
| GET `/enrollment-history?page=N` | Immutable before/after enrollment history, 50/page |

The normal workflow uses labeled native controls, loading/retry/conflict states,
dark selects, keyboard forms and wrapping mobile layouts. Saved assignments survive
experiment revision refreshes, and identical failed commands retain request keys.

## Backup and release blockers

Schema compatibility remains exact. **0016 app and privileged helper bundles must
match before rollout or 0016 archive restoration.** Neither a 0015 helper nor an
older schema catalog can validate a 0016 archive. Preserve the matching 0015
application/helper and verified external pre-upgrade backup for rollback. Do not
weaken schema validation or writer fencing.

A separately reviewed matching helper update and successful isolated privileged
restore/startup-failure rollback/interrupted-recovery acceptance remain release
blockers. The historical 2G `/proc` writer-inspection limitation remains documented.
No privileged acceptance or production helper update is claimed here. Existing
Docker/Compose settings, storage roots, UID/GID, photos, backups and credentials
remain intact. Rollback uses stopped writers and a verified matched backup/code/
helper set, replacing only the four persistent data children.

## Verification and deferred work

Final verification: **393 backend tests passed**, including **23 focused 2H.2
acceptance tests**; **205 frontend tests passed**, including **7 new participant
workflow tests**. The final focused rerun also exercised a real second flush and
confirmed it does not create another treatment unit. Production TypeScript/Vite
build passed.

Real Chromium checks passed for the new Enrollment workflow and the existing
Experiment Foundation, Fruiting, Genetics/Magic Kingdom and Environment workflows.
Enrollment acceptance exercised existing records, precommitted multi-recipe
creation, prospective/retrospective mixed membership, shared-source counts, reviewed
exclusion/history and mobile overflow. Browser acceptance caught a parent-revision
refresh clearing saved assignment form state; this was fixed and regression-tested.

Backend checks include historical plan/group ownership, own-FR unit constraints,
exact replay, stale revisions/fingerprints, mixed/possible ancestry, physical
transfer-chain associations, source correction/explicit Keep semantics, late-failure
rollback, changed plan/recipe rejection, 0015 row preservation, repeated upgrades,
model/schema consistency, immutable history and isolated native backup extraction.
All databases and browser fixtures were disposable.

The existing Starlette/AnyIO deprecation warning remains. Vite reports a nonblocking
roughly 527 kB JavaScript chunk warning. No application dependency or lockfile was
changed. Optional Playwright/formatters were used only as temporary development tools.
The managed executor required local socket/network permission for TestClient and
native browser servers; no application safety check or assertion was weakened.

Reproduce from repository root:

```sh
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test -- --maxWorkers=1 --testTimeout=15000 && npm run build)
# Optional Python Playwright package and installed Chromium are required:
.venv/bin/python scripts/experiment_enrollment_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/experiments_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/fruiting_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/genetics_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/environment_browser_smoke.py
```

Production Docker build/deployment acceptance, matching privileged helper installation
and isolated privileged 0016 restore/rollback acceptance were **not performed**.
They remain release work; no Debbie access, production cultivation change or
production helper update occurred.
Environmental scheduling, sequential trial attribution/coverage and shared tent
assignment workflows remain 2H.3; harvest comparisons and automatic Grow Insights
remain 2H.4; production/recovery release acceptance remains 2H.5. Sensors and device
control remain excluded.
