# Milestone 2D.1 — Performance dashboard and cultivation comparisons

Built from merged 2C.4 on `main` (`04fbbe716fe290326e6261998203042ddad09eaa`), on `feature/milestone-2d1-performance`. Reports is now a read-only performance dashboard. No new cultivation procedure, input requirement, accounting, genetics workflow, sensor, potency ranking or predictive recommendation is introduced. No merge or deployment is automatic.

## Primary metric and coverage

The primary metric is **average measured wet harvest yield per completed fruiting container**, in grams. A permanent FR is one container observation. All its harvest entries across every flush are summed first; averaging harvest entries directly would give multi-harvest containers extra weight and is deliberately avoided.

A container qualifies only when its terminal outcome is Completed, at least one harvest entry exists, and every harvest entry has a recorded wet weight. Measured zero qualifies. No harvests, all-null wet weights or partially measured wet weights exclude a completed container from the primary average, with exclusion counts shown. Active and Failed containers never contribute to that average.

Known wet totals have a different purpose: they sum actual recorded wet entries from the period's Completed and Failed containers, including partially measured containers. Both completed-known and failed-known subtotals are available. Active weights are excluded. No measurements yields Unknown, not zero. Coverage shows measured entries/entries and qualifying/excluded containers, so these known totals cannot be mistaken for complete yields.

SQL sums integer milligrams and Python uses Decimal for totals/averages. Averages and percentages are rounded to three decimal places with half-up rounding; API decimals serialize as strings. Wet and dry are never substituted for one another. The optional completed-container dry average requires at least one harvest and all dry weights recorded, using its own sample count regardless of wet coverage.

Each comparison shows qualifying container count and distinct known source spawn count **among those qualifying containers**, plus the count without a known spawn source. Multiple containers sharing one spawn bag remain separate FR observations; the shared source IDs remain linked and are explicitly not presented as independent genetic trials.

## Filters and populations

Three primary filters are visible: Species / Strain, Time Range and Group Results By (Strain, Genetic culture line, Substrate recipe). All time is the default. Last 30/90 days use the browser's local calendar date, include today, and send explicit inclusive start/end dates. Custom dates require a valid ordered pair in the UI. The API also supports a single open-ended date bound.

Completion dates select Completed records; failure dates select Failed records. Harvest dates do not select the reporting population. Selected terminal counts, out-of-period counts and excluded undated terminal counts are displayed. All time includes known terminal statuses even when their outcome date is unknown; bounded periods exclude these undated records without inventing a date.

Active/nonterminal records appear separately as the current population, with the species/strain filter applied. They have no terminal date to filter, are explicitly labeled as not date-filtered, and are excluded from terminal failure rates and completed yield/timing averages. Archived records retain all their recorded historical outcomes and measurements and are included.

Species options use explicitly recorded strain scientific names, not inferred taxonomy. A fruiting record matches a species only if every documented contributing source has that same nonempty recorded scientific name. A specific strain filter requires a fully identified single strain; it excludes mixed/partial identities rather than treating a known contribution as the complete identity.

## Genetics and provenance

Operational runs use their permanent original spawn source. Legacy shared mixtures use the batch's shared sources; specific allocations use only the sources linked to that FR. Acquired fruiting material uses its acquired culture line without inventing a spawn source. Archived source records remain resolvable.

Different known lines of the same strain may share a strain group; they remain separate culture-line groups. Mixed, partial and unknown genetic identities use explicitly unranked coverage buckets, not synthetic strains or lines. A documented culture line with an unknown strain still has a valid permanent line identity and can be compared as that line. Grouping never combines clones, isolates or parents into an invented genetic identity.

The chart ranks only identified groups with qualifying measurements. Fewer than three qualifying containers is marked **Preliminary**. An empty/insufficient dataset gives explicit guidance. No superiority, experimental independence or breeding claims are made. Record drill-downs retain permanent FR IDs, strain/line identity, source IDs and outcome/coverage information. Reusing an F-label never combines unrelated grows.

## Recipes, growth speed, flushes and outcomes

Substrate comparisons group by original recipe ID and use immutable saved grow snapshots. The current editable recipe is never consulted for historical formulation/name/revision. The group name comes from its earliest available saved revision; each recorded revision can be expanded to see its historical name, ingredients, instructions, optional dry average and source FR records. Missing snapshots remain unknown. Recipe comparisons are observational: genetics and growing conditions can differ.

Growth-speed averages use completed containers with the required recorded dates, independently of wet measurement coverage. They show average spawning-to-first-pinning, spawning-to-first-harvest and completed-cycle duration, with valid and missing counts for each metric and group. Missing/invalid chronological pairs remain Unknown. Legacy history is never backfilled.

Flush comparisons use only selected Completed containers. Each FR/flush is one observation. A flush needs at least one harvest and all wet weights recorded to enter its average. Reached-container counts include existing recorded flush rows even when unmeasured; no missing or unrecorded flush is inserted as zero. Measured sample counts, incomplete exclusions, known partial totals and contributor IDs are separate, making later-flush attrition visible.

Terminal failure rate is `Failed / (Completed + Failed)` for the selected terminal population. The numerator and denominator are visible; no terminal records gives Unknown. A grow with harvests followed by Failed stays Failed for outcomes and retains those harvests in known totals. Failure notes are not parsed into categories.

## API and architecture

`GET /api/reports/performance`

Query parameters:

- `group_by`: `strain` (default), `line`, or `recipe`.
- `strain_id`: optional tracked permanent strain ID.
- `species`: optional exact recorded scientific-name option.
- `start_date`, `end_date`: optional inclusive ISO calendar dates.

Invalid dates, reversed bounds, unsupported grouping and unknown strain/species filters return 422. The typed response includes the selected period, filter options, summary statistics, comparison groups/revisions, per-flush coverage, terminal observations and a separate current active population. Permanent IDs drive every join and drill-down.

`reports.py` performs four SELECT statements per report regardless of container count: catalog options, per-FR harvest/date/label aggregates, bulk source/identity resolution and per-flush aggregates. It reads a consistent transaction snapshot, then performs Decimal/group calculations in memory. It does not call individual record-detail endpoints, load photographs or write/cache analytics. Only fields needed from record/run/state models are loaded. `report_schemas.py` defines Pydantic response contracts.

`Reports.tsx`, `PerformanceBars.tsx` and `reportApi.ts` reuse the existing Reports navigation, page headers, shared CollapsiblePanel, error/retry handling, button styles and dark theme. Horizontal bars are CSS with labeled numeric values and sample counts. Accessible tables, saved revisions, underlying records, growth speed, flushes and data-quality rules are independently expandable. Filters and controls wrap on phones; wide tables scroll internally without page overflow. No charting dependency was added.

## Validation and limits

Regression coverage includes per-container/multi-harvest/multi-flush averaging, shared-source counts, true zero, missing/partial wet/dry weights, all outcomes, failed harvests, known/mixed/partial genetics, shared/specific allocations, acquired FRs, archived history and reused labels, snapshots/revisions, dates/sample counts, inclusive period/species/strain filters, insufficient datasets, read-only behavior and fixed query count. Frontend tests cover charts/tables, filters/presets, coverage text, drill-downs, revision inspection and errors/retries. The reporting browser suite uses actual typed creation APIs and checks unchanged grow history after reporting, plus desktop/phone/tablet layouts and keyboard access.

Limitations are intentional: current active records cannot have a terminal reporting period; missing historic dates/measurements/recipe snapshots stay unknown; scientific names reflect recorded metadata rather than a new taxonomy; and small observational samples do not establish causal or genetic superiority. This personal-workspace implementation computes results on request without a persisted cache or background reporting service.

No migration is required. Existing models, migration 0013, cultivation mutations/idempotency, label reuse, source relationships, LC accounting, recipe snapshots, photographs and historical events are preserved. Tests use disposable local databases; no existing user data is reset or deployed.

Final validation passed: **197 backend tests** (including 18 reporting cases), **143 frontend tests** across thirteen files, production TypeScript/Vite build, all five existing Chromium browser suites and the new reporting-specific browser suite. Fresh Alembic upgrade/current/check remains at **0013_journal_photos**, with no schema drift or new migration. `git diff --check` passed. One existing upstream Starlette/AnyIO deprecation warning remains; no final test or build failures. No existing database/photo data was reset, and no merge or deployment was performed.
