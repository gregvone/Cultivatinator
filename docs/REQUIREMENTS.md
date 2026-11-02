# Requirements and implementation status

## Implemented — Milestone 1

Docker/Compose foundation; same-origin frontend/backend; responsive industrial console shell with seven routes; typed zero/empty dashboard summary; attention, cultivation, activity, and environment empty states; safe application information; SQLite initialization, migration baseline and health checks; persistent directory layout; tests and operational documentation. No cultivation records are seeded.

## Implemented — Milestone 2A

Single Strain Catalog (optional scientific name; no separate species table), independent acquired culture lines, spore sources with optional strain, transactional batch physical-container registration, immutable sequenced IDs, descriptive editing, archive/restore without relationship loss, photo-card-first search/filter views, individual details, multiple photos/cover/viewer/removal, validated originals and generated thumbnails, per-record activity, and real active-physical-culture dashboard counts. Quantities are initial registrations only. See [operations](MILESTONE_2A.md) for constraints and update procedures.

## Implemented — Milestone 2B

Universal acquisitions for culture/spores, colonized spawn jars/bags (SJ/SB, Ready or Colonizing), and acquired GB/FR bags/blocks; explicit line origins and confirmed/possible genetic parents; successful spore-derived lines, tissue clones and selected isolates; manual spore collection; prepared and acquired grow batches; shared-mixture and per-container source allocations; mixed-line/strain warnings; related source/descendant browsing; revision-protected ancestry corrections with previous values retained in history; photos/activity/archive for all new records; real spawn and fruiting dashboard counts. Additive migrations preserve 2A data. Provenance is manual and does not consume source material. See [2B operations](MILESTONE_2B.md).

## Implemented — Milestone 2C.1

Dashboard Quick Create with six dedicated material entries; context-sensitive active source choices and validated source preselection; source-detail Create From This; Inventory-owned external acquisition and strain management; compatible legacy URL redirects; uncluttered Culture Library reference navigation. The existing spore collection endpoint powers New Spore Print. Other operational entries clearly defer execution without new records or consumption. No models, migrations or backend operations changed. See [2C.1](MILESTONE_2C1.md) and the staged [approved future commitments](ROADMAP.md#milestone-2c-staged-delivery).

## Implemented — Milestone 2C.2

Explicit stock balances/unknown usage, manual reasoned adjustments, immutable ledger/audit history, pooled reusable capacity and one-time release, generic inventory categories/storage and exact compatible weight/volume conversions (no seeds), dedicated agar/grain/LC/substrate recipe definitions and comparison with historical snapshots, Inventory preparation with individual permanent identities and automatic Ready to Inoculate (legacy Preparing records retain explicit readiness), partial/bulk inoculation/transfers/filling, exact physical source links, preserved routine genetic lines, pending independent spore establishments, measured LC depletion/corrections, lifecycle Complete/Failed controls, inventory/recipe/prepared/history UI and additive migrations. Existing 2B data/photos/FR identity and 2C.1 navigation remain compatible. See [2C.2 scope/operations](MILESTONE_2C2.md).

## Approved future requirements — not implemented

- Detailed growth/laboratory observations, germination monitoring and failed cloning-attempt workflows. Preparation, routine transfers and record-level failure are implemented in 2C.2. Successful cloning and spore collection are implemented in 2B.
- Detailed colonization observations, fruiting automation, flushes and individual harvests; actual spawning/FR substrate allocation remains 2C.3. Grain preparation and inoculation are implemented in 2C.2. Acquired spawn, manual stages and GB/FR provenance are implemented.
- Detailed physical propagation operations, multiple-source laboratory operations and an interactive genealogy editor. Explicit genetic ancestry and manual grow contributions are implemented. Permanent identifiers and individually registered batch containers are implemented in 2A.
- Biological inventory, raw materials, supplies, consumables, reusable containers, equipment and storage locations; reusable laboratory/substrate recipes; automatic transactional inventory deductions, partial consumption and cost accounting. Initial quantities and optional descriptive per-container purchase prices are implemented in 2A.
- Laboratory observations, non-photo file attachments, environmental temperature/humidity/growing-area records, and cross-module activity. Culture Library photos and history are implemented.
- Statistics and reporting for cultivation progress, colonization times, harvest yields, culture performance, contamination, inventory use, and cost/performance analysis.
- Complete downloadable backup and restore containing database, photos, managed files and persistent settings.

See architectural constraints before implementing these modules. Preserve history, correction traceability, precise quantities and atomic writes.

## Deferred / excluded from this milestone

The future requirements above remain deferred; manual provenance must never be mistaken for an executed consumption transaction. Optional sensor integrations come later. No alert engine, general-purpose file uploads, backup buttons, QR generation, label printing, PWA, authentication, user registration, multiuser permissions, cloud database, paid APIs, microservices, or production deployment is included. V1 is single-user on a trusted private network. Dashboard placeholder pages describe future scope and do not offer pretend actions.
