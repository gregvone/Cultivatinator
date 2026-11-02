# Roadmap

1. **Application Foundation** — complete: shell, empty dashboard/API, SQLite/Alembic, Docker storage/deployment, tests and docs.
2. **Culture Library 2A** — implemented: single strain catalog, acquired lines, spores, batch physical containers, permanent IDs, photos/thumbnails/cover management, archive/restore, search and per-record histories.
3. **Culture Ancestry and Grow Provenance 2B** — implemented: universal acquisitions; SJ/SB and GB/FR foundations; explicit genetic origins and confirmed/possible parents; successful spore cultures, clones and isolates; manual spore collection; shared/specific grow allocations; source/descendant browsing; photos, history and safe ancestry correction. Detailed genealogy editing is deferred.
4. **Inventory and Reusable Recipes** — materials, equipment, locations, purchase costs and precise transactional quantities.
5. **Laboratory Management** — growing cultures, agar batches, individual plates, liquid cultures, germination, transfers and observations.
6. **Spawn Production** — preparation, grain, jars/bags and colonization.
7. **Fruiting and Harvest Tracking** — growing units, flushes, harvests, cloning and spore collection links.
8. **Dashboard Enhancements, Environmental Tracking, and Reporting** — database aggregates, attention items, timelines, manual conditions, yield/performance statistics. Sensor integrations are optional future work.

Culture Library photographs are implemented. Complete downloadable backup/restore remains deferred; use stopped-service whole-data backups before upgrades. Future milestone details remain subject to design approval. Milestone 2B documents provenance only: actual spawning, transactional consumption and prevention of double consumption belong to later operational workflows. Successful clones and manual spore collection are implemented, while failed attempts, monitoring and harvest accounting remain deferred.

## Milestone 2C staged delivery

**2C.1 — implemented interface foundation:** Dashboard Quick Create, dedicated context-sensitive material entries, Create From This source preselection, Inventory-owned outside acquisition/strain management and a cleaner reference Culture Library. Existing completed spore collection works; deferred entries perform no operational writes. See [2C.1 operations](MILESTONE_2C1.md).

**2C.2 — approved, not implemented:** preparation and inoculation are separate steps; actual agar/LC transfers and spawn inoculation retain the correct genetic line. Bulk creation assigns an individual permanent ID to every physical record. Introduce known inventory balances and atomic deductions with sufficient-balance validation, reusable spawn jars versus disposable spawn bags, and explicit Ready confirmations. Saved recipes support optional processing details, use-by dates and prepared substrate inventory. Planned starting pooled reusable inventory is **20 agar plates and six 6-quart shoebox fruiting trays**, not demo records or seeded balances in 2C.1. Explicit Complete/Failed actions release reusable containers according to the actual lifecycle.

**2C.3 — approved, not implemented:** real spawning and consumption, with individual FR identity per tray even when trays share a GB. Record each tray's spawn/substrate quantities and editable ratio calculations; validate/deduct known stock atomically and prevent duplicate consumption. Add dated observations, bulk status updates and contamination warnings through physical provenance. Do not infer genetic hybridization or propagate assumptions as confirmed ancestry.

Future purchase and supply tracking belongs under Inventory. Reusable container pools, saved recipes, preparation batches, bulk operational creation, balances/deductions, actual inoculation/transfers, spawn-to-bulk consumption, observation timelines and contamination propagation are deliberately not executed by 2C.1. These requirements remain approved for the following stages. Stage assignments can be refined without dropping the commitments above.
