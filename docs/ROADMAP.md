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

**2C.2 — implemented:** separate preparation and inoculation/filling for agar, LC containers/syringes and spawn jars/bags; individual permanent identities within bulk sessions; explicit known/unknown balances, immutable adjustments/usage history and atomic deductions; reusable pools and one-time Complete/Failed release; agar/grain/LC recipes with actual historical snapshots, optional processing, shelf-life/use-by warnings and explicit Ready to Inoculate confirmation. Suggested openings of **20 reusable agar plates and six 6-quart shoebox trays** require user confirmation; nothing is seeded. Tray reservations and prepared bulk-substrate inventory are not operational in 2C.2. See [2C.2 details](MILESTONE_2C2.md).

**2C.3 — approved, not implemented:** real spawning and consumption, with individual FR identity per tray even when trays share a GB. Prepared bulk-substrate inventory remains an approved future requirement and must have complete accounting before it becomes operational. Record each tray's spawn/substrate quantities and editable ratio calculations; validate/deduct known stock atomically and prevent duplicate consumption. Add dated observations, bulk status updates and contamination warnings through physical provenance. Do not infer genetic hybridization or propagate assumptions as confirmed ancestry.

Future purchase and supply tracking belongs under Inventory. Reusable container pools, saved recipes, preparation batches, bulk preparation/inoculation and balances/deductions are implemented in 2C.2; they were deliberately not executed by 2C.1. Spawn-to-bulk consumption, observation timelines and contamination propagation remain 2C.3. These requirements remain approved for the following stages. Stage assignments can be refined without dropping the commitments above.

2C.2 now implements the preparation/inoculation, recipe, explicit balance, reusable-pool and transactional deduction commitments above; see [operational details](MILESTONE_2C2.md). Suggested 20-plate/six-tray openings require user confirmation. Tray reservation and actual spawning, FR substrate ratios/allocations, advanced observations and contamination propagation remain 2C.3. Purchase tracking and built-in backup/restore remain deferred.
