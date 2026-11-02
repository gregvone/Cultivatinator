# Requirements and implementation status

## Implemented — Milestone 1

Docker/Compose foundation; same-origin frontend/backend; responsive industrial console shell with seven routes; typed zero/empty dashboard summary; attention, cultivation, activity, and environment empty states; safe application information; SQLite initialization, migration baseline and health checks; persistent directory layout; tests and operational documentation. No cultivation records are seeded.

## Approved future requirements — not implemented

- Species and strains; genetic culture lines; acquired cultures and spore collections; spore sources, lineage relationships and culture histories.
- Agar preparation and individual plates, growing cultures, liquid culture preparation, transfers, laboratory observations, spore germination, mushroom tissue cloning and spore collection.
- Spawn jars and bags, grain/spawn preparation and colonization; fruiting blocks, bags, trays, and other containers; flushes and individual harvests.
- Genetic ancestry and physical propagation history, multiple-source operations, permanent identifiers, individually tracked children of batches, and interactive lineage visualization.
- Biological inventory, raw materials, supplies, consumables, reusable containers, equipment and storage locations; reusable laboratory/substrate recipes; automatic transactional inventory deductions, partial quantities, purchase prices and basic costs.
- Observations, activity histories, photographs and attachments, environmental temperature/humidity/growing-area records.
- Statistics and reporting for cultivation progress, colonization times, harvest yields, culture performance, contamination, inventory use, and cost/performance analysis.
- Complete downloadable backup and restore containing database, photos, managed files and persistent settings.

See architectural constraints before implementing these modules. Preserve history, correction traceability, precise quantities and atomic writes.

## Deferred / excluded from this milestone

All future requirements above remain deferred. Optional sensor integrations come later. No alert engine, uploads, backup buttons, QR generation, label printing, PWA, authentication, registration, multiuser permissions, cloud database, paid APIs, microservices, or production deployment is included. V1 is single-user on a trusted private network. Dashboard placeholder pages describe future scope and do not offer pretend actions.
