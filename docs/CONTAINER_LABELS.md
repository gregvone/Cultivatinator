# Physical container labels and culture lifecycle

Milestone 2C.2 separates the label written on a physical container from its permanent biological record. Everyday headers, growing lists, source choices, Quick Create results and Active Cultivation summaries show the physical label first. Copy Labels copies the physical labels. Permanent AG/SJ/SB/LC/FR IDs stay accessible and are the only keys used for lineage, photographs, provenance and URLs. Reusing P-05 never reuses AG-0012 or changes its history.

| Container | Physical label | Reusable |
| --- | --- | --- |
| Agar plate | P-01 | Yes |
| Spawn jar | J-01 | Yes |
| Spawn bag | B-01 | No |
| LC jar | L-01 | Yes |
| LC syringe | LS-01 | No |
| Reusable fruiting tray/container | F-01 | Yes |
| Disposable fruiting bag/block | FD-01 | No |

Labels expand naturally to P-100 and beyond. Trays default reusable; bags/blocks are disposable. Other fruiting containers require an explicit reusable choice; otherwise they are disposable. No initial equipment counts or inventory setup exists.

## Allocation and history

New registrations, acquisitions, direct creation, successful establishments and clones/isolate physical registrations allocate automatically. The lowest free reusable label wins; otherwise the next never-issued number is generated. Disposable numbers always advance. Optional Available Labels choices select another free label or explicitly add a new one. An occupied label produces a clear conflict and rolls back the entire operation.

Existing SQLite immediate-write transactions serialize allocation and destination creation. Database unique indexes prohibit simultaneous active assignments. Bulk creation and all source usage share the same transaction; request keys replay committed results without allocating or consuming twice. New manual codes must match the next issued code; use Add a new physical label to avoid stale number guesses.

Each assignment is retained with its permanent owner, assignment timestamp, optional release date and reason. Immutable label definitions and released-assignment triggers prevent rewriting history. Active reusable containers may explicitly Change Label, preserving the old assignment. Disposable labels cannot be relabeled/reused. Physical labels can appear in multiple historical rows, always disambiguated by permanent IDs and lifecycle status.

## Lifecycle rules

- **Agar:** Quick Create starts **Germinating** with the actual inoculation date (the existing internal `colonizing` value is retained). Mark Ready records a local-default date with override. Only Ready agar is a source. One successful creation/inoculation operation may produce many destinations; after all succeed, the donor becomes Used once and releases P once. Failure anywhere rolls back destinations, deductions, consumption and release. Used agar cannot supply a later operation. Mark Failed permits an optional reason/notes/date and releases P immediately.
- **Spawn:** Quick Create starts Colonizing; Mark Ready for Spawning is explicit and dated. Failure releases J; B remains a unique historical disposable number. Actual Ready→Used spawning is implemented in [2C.3](MILESTONE_2C3.md), consuming one whole source for all destinations. Manual 2B grow provenance never consumes spawn or releases its label.
- **LC:** measured withdrawals remain partial and transactional. Zero volume is Depleted, preventing transfers while retaining L occupancy. Complete / Retire Container or Mark Failed explicitly closes the record and releases L. LS labels are unique disposable identifiers. Media default/inheritance and correction audits are unchanged.
- **Fruiting:** existing 2B/acquired registration assigns F or FD without inventing spawning/substrate events. F remains occupied until Complete Growing Cycle or Mark Failed. A stage change to Finished also represents explicit completion. Registering an explicitly finished cycle retains a released historical assignment. Harvests/flushes do not release labels; [2C.3](MILESTONE_2C3.md) provides their operational UI and explicit Finish Grow.
- **Pending spores:** inoculated agar receives P and Germinating without inventing a culture line. Successful establishment retains the same permanent AG ID, label and inoculation date. Pending failures release P and prevent later establishment.

Archiving only changes visibility. It never releases a label. Restore also never reopens terminal cultures or claims released containers. Lifecycle date overrides record user-supplied dates; server timestamps still audit the operation. Legacy terminal APIs keep their accounting semantics, while the normal status panel supports optional failure reasons.

## Migration and legacy records

**0010_containers**, following 0009_lc_default, adds `container_labels`, `label_assignments` and `cultivation_states` with typed foreign keys to existing physical/spawn/fruiting/pending records. Partial unique indexes enforce one active label per owner and one active owner per label. Prior migrations are unchanged. No old record, quantity, ID, snapshot, photo, acquisition, provenance or recipe is rewritten. No historical labels or readiness dates are guessed.

All agar views use the same cultivation status: Germinating, Ready, Used, Failed, or **Readiness not recorded** when absent. Record visibility (`status=active/archived`) is separately labeled and never implies readiness. The normal agar detail page has one prominent status panel with Mark Ready and Mark Failed; it has no Complete/Failed selector. Historical preparation closure remains available separately, with no preselected completion action. Quick Create and historical inoculation verify an agar source before each new creation/transfer command; transactional backend validation checks again before committing. Retrying the same request key retrieves its original result, even if the first response was lost after the plate became Used. Editing the request triggers a fresh readiness check.

Legacy active records without labels show **Assign Label**. Legacy agar with missing growth state shows Readiness not recorded and must explicitly Mark Ready before supplying a new operation; legacy spawn readiness remains readable. New readiness/failure actions can transition eligible old records. Terminal history cannot occupy a new label. Old request results still replay as originally recorded, including results predating physical labels. The normal interface has no new stock or equipment prerequisite. Historical preparation pools/ledger APIs retain exactly-once releases and existing reservations.

Downgrade refuses to discard any label/lifecycle history. Restore the matching stopped-data backup with the matching previous application if rollback is needed; do not delete these tables or reset migration state.

## API additions

Existing record schemas have additive `physical_label`, `label_reusable`, `label_occupied`, `growth_stage` and lifecycle date fields. Existing API routes and permanent-ID URLs remain compatible.

- `GET /api/containers/available?material_type=agar_plate` returns free labels and the next new label (optional `reusable` for fruiting).
- `GET /api/containers/records/{kind}/{id}` returns tracking state and assignment history.
- `POST /api/containers/records/{kind}/{id}/label` assigns/changes a label with `request_key`, optional `label` or `new_label`, and optional reusable choice for other fruiting containers.
- `POST /api/containers/records/{kind}/{id}/state` accepts `request_key`, `action` (`ready`, `failed`, `complete`), optional `action_date`, `reason`, `notes`.
- Direct creation accepts optional per-destination `label_choices`; manual grow containers accept optional `label_choice`. Automatic allocation is the default.

## Validation

Physical-label correction verification: **142 backend tests**, **86 frontend tests** across eight files, and the production build passed. Fresh/repeated Alembic upgrade, current and check passed at **0010_containers**, with no schema drift; empty-history downgrade/re-upgrade and a populated 0009 legacy upgrade are also covered. All four browser smoke scripts and the local Docker build/recreation check passed. One existing upstream Starlette/AnyIO deprecation warning remains. Initial outdated UI assertions and fixture assumptions were corrected; no final failures remain. Browser scripts use permanent IDs to open records and assert physical labels as the primary visible identifiers. Docker checks use a disposable local volume, UID 10001 and port 8085, then recreate the container to verify retained labels, releases, history, idempotency, LC balances/media, lineage, FR identity and photographs. No deployment is performed.

### Agar readiness correction

This correction requires **no migration** and preserves internal `colonizing` values, recorded dates, permanent IDs, label allocation/release, lineage, photos, recipes, acquisitions and LC accounting. Germinating is a display name for agar only; spawn still displays Colonizing. LC and spore source eligibility does not depend on agar readiness. Regression coverage includes status consistency across views, legacy explicit readiness, source exclusion and invalidation before submission. Validation passed: **145 backend tests**, **98 frontend tests** across nine files, the production build, and all four browser smoke suites. Browser coverage verifies Germinating/Ready/Used/Failed status, legacy readiness, eligibility across agar/LC/spawn destinations, stale-source rejection before POST, label reuse, existing LC/spore/spawn behavior and desktop/mobile layouts. One existing upstream Starlette/AnyIO deprecation warning remains. No final test or build failures remain.
