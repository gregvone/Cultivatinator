# Requirements and implementation status

## Implemented — Milestone 1

Docker/Compose foundation; same-origin frontend/backend; responsive industrial console shell with seven routes; typed zero/empty dashboard summary; attention, cultivation, activity, and environment empty states; safe application information; SQLite initialization, migration baseline and health checks; persistent directory layout; tests and operational documentation. No cultivation records are seeded.

## Implemented — Milestone 2A

Single Strain Catalog (optional scientific name; no separate species table), independent acquired culture lines, spore sources with optional strain, transactional batch physical-container registration, immutable sequenced IDs, descriptive editing, archive/restore without relationship loss, photo-card-first search/filter views, individual details, multiple photos/cover/viewer/removal, validated originals and generated thumbnails, per-record activity, and real active-physical-culture dashboard counts. Quantities are initial registrations only. See [operations](MILESTONE_2A.md) for constraints and update procedures.

## Approved future requirements — not implemented

- Culture ancestry/lineage relationships (Milestone 2B), spore-to-culture establishment, cloning and isolates. Strain classification remains a single catalog.
- Agar preparation and individual plates, growing cultures, liquid culture preparation, transfers, laboratory observations, spore germination, mushroom tissue cloning and spore collection.
- Spawn jars and bags, grain/spawn preparation and colonization; fruiting blocks, bags, trays, and other containers; flushes and individual harvests.
- Genetic ancestry and physical propagation history, multiple-source laboratory operations and interactive lineage visualization. Permanent identifiers and individually registered batch containers are implemented in 2A.
- Biological inventory, raw materials, supplies, consumables, reusable containers, equipment and storage locations; reusable laboratory/substrate recipes; automatic transactional inventory deductions, partial consumption and cost accounting. Initial quantities and optional descriptive per-container purchase prices are implemented in 2A.
- Laboratory observations, non-photo file attachments, environmental temperature/humidity/growing-area records, and cross-module activity. Culture Library photos and history are implemented.
- Statistics and reporting for cultivation progress, colonization times, harvest yields, culture performance, contamination, inventory use, and cost/performance analysis.
- Complete downloadable backup and restore containing database, photos, managed files and persistent settings.

See architectural constraints before implementing these modules. Preserve history, correction traceability, precise quantities and atomic writes.

## Deferred / excluded from this milestone

All future requirements above remain deferred. Optional sensor integrations come later. No alert engine, general-purpose file uploads, backup buttons, QR generation, label printing, PWA, authentication, user registration, multiuser permissions, cloud database, paid APIs, microservices, or production deployment is included. V1 is single-user on a trusted private network. Dashboard placeholder pages describe future scope and do not offer pretend actions.
