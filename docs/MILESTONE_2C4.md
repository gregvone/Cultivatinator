# Milestone 2C.4 — UI and workflow polish

This milestone starts from merged 2C.3 (`aa41ee5835ed2224af207132f3865220a37d1433`). It changes presentation only. There are no backend/API, schema/migration, lifecycle, label allocation, photo ownership/storage, lineage, accounting or recipe-snapshot changes. No deployment or merge is automatic.

## Shared controls

`CollapsiblePanel` uses native details/summary with a heading, optional summary, chevron, expanded state and a controlled content relationship. The whole heading is clickable; Enter/Space work with native keyboard behavior. Panels expand independently and do not persist preferences. Children remain mounted when closed, preserving unsaved inputs and pending photo queues. Native invalid events open their collapsed ancestors synchronously before focus; field validation attributes and inline error alerts also reveal their containing panels.

`RecordHeader` gives culture-library records a consistent physical-label/name, actual cultivation status, dates, known source/origin and measured balance hierarchy. Permanent IDs remain visible in smaller text and in record history. `RecordNextAction` offers existing eligible Quick Create links in compact growing lists; it uses the existing source-eligibility helper and does not perform mutations.

Shared button styles give ordinary actions an outlined/subtle fill, the next routine action a primary fill and terminal operations a distinct warning style. Existing confirmation forms and delete dialogs remain in place. Focus indicators, wrapping and 44px touch targets apply throughout. Edit Harvest is now an explicit secondary button. The shared application header and sidebar no longer carry milestone badges.

## Fruiting journal

The fruiting header keeps stage, current flush and actual measured wet/dry yield totals visible. Null measurements remain Unknown; measurement counts and timing remain in Detailed Results. Routine next actions appear before terminal actions. Finish Grow stays available without taking the primary-action style.

Current Growing Cycle opens for active grows. Opening a lifecycle action reveals its form; manually collapsing the panel preserves the form and selected files. Saved-event/photo retry controls remain available after completion, including successful and failed history refreshes.

Grow Journal opens initially. The current/most recent numbered flush opens; older flushes start collapsed with recorded yield/harvest summaries. Opening one flush does not close another. Pinning, Fruiting and individual Harvest entries retain their exact dates, notes, potency and photo galleries. Grow Completed remains a separate dated entry with its closing notes and photos. Legacy unknown dates are not filled in.

Compact galleries show the first three thumbnails and offer Show all when needed; the original viewer is unchanged. Add Photos reveals the existing upload, cover and removal controls. Closing either photo controls or ancestor panels keeps pending uploads mounted. All paths continue to use exact permanent FR IDs, numbered stage events and HR IDs. Measurement revisions stay collapsed.

Source & Genetics, Substrate & Environment, Detailed Results, general record information/photos and Record History start collapsed. The biological journal stays separate from the audit trail. No separate journal/photo workspace was added.

## Other sections

- Dashboard: summary counts, Needs Attention, Active Cultivation and Quick Create remain prominent; environment observations and secondary activity start collapsed. Stale inventory/transfer roadmap text was removed. Quick Create uses a compact two-column phone layout.
- Culture Library / Laboratory: identity, actual status, readiness actions, editing and Create From This remain discoverable. Genealogy, preparation/transfer details, general photos, related records and audit events are secondary panels. LC balance controls remain accessible outside historical snapshots. Navigating to another record resets panel defaults.
- Cultivation: compact spawn/fruiting listings retain labels, strains, statuses, dates, short source/recipe context and existing action links.
- Acquisitions: material identity, supplier/origin and acquisition date remain visible; optional supplier references use a collapsible form section. Records continue to use Culture Library.
- Recipes: names, categories, ingredients, instructions and primary actions remain visible; processing/secondary metadata are collapsed. Optional processing form inputs use the same component. The default LC Media workflow is unchanged.
- Settings: optional fruiting-tent configuration, application information and backup guidance use consistent panels without new settings requirements.
- Reports: the existing placeholder is compact and identifies that reports are not yet available; planned views are collapsed. No analytics were added.
- Quick Create: required source/recipe/count/date inputs remain visible. Optional notes, quantities and manual label overrides use the shared panels.

## Validation

Frontend regressions cover panel defaults, independent expansion, retained input nodes/values, validation disclosure, current/older flush defaults, primary/terminal styling, completed entries, thumbnail limits, exact photo paths and pending retry state across collapse/expand. Chromium verifies Enter/Space, validation focus inside a closed panel, retained notes and photos, journal defaults, mobile touch sizes and page overflow. Existing browser suites still exercise acquisitions, lineage, Ready agar transfers, LC accounting, multiple FR destinations, multiple flushes/harvests, every journal photo type and F-label release/reuse.

Remaining scope: Reports and other previously deferred capabilities remain unavailable. Expansion choices intentionally reset on a new visit. This milestone does not introduce new cultivation capabilities.

Final validation: **179 backend tests** passed (one existing upstream Starlette/AnyIO deprecation warning), **133 frontend tests** across twelve files passed, and the production build passed. All five Chromium smoke suites passed: Culture Library/gallery, lineage/provenance, Quick Create, preparation/Laboratory and fruiting/journal. The fruiting suite additionally checks phone/tablet overflow, 44px controls, keyboard disclosure, native invalid-field focus, persisted pending files and completion retry without duplicate actions. No final test/build failures remain. No database migration was added or required; backend files are unchanged.
