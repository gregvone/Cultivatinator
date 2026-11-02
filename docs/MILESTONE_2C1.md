# Milestone 2C.1 — Quick Create and reference browsing

Current behavior and the user-confirmed co-located Debian deployment layout are described in [Milestone 2C.2](MILESTONE_2C2.md). Earlier deferred-operation and separate/unknown checkout-location descriptions in this historical milestone document do not override 2C.2.


This increment changes interface responsibilities only. It starts from merged Milestone 2B, including FR strain correction `baa171e`. It adds no models, migrations, runtime dependencies or operational backend endpoints. Existing IDs, photographs, genetic lineage, physical provenance and histories remain intact. Port 8085, the non-root Docker/Compose architecture and persistent `/data` mapping are unchanged. Debian deployment data remains `/storage/tv/cultivatinator`; no server access, deployment or merge is performed.

## Responsibilities and working actions

- **Dashboard → Quick Create:** six icon entries near the bottom, each with a dedicated material workflow and appropriate source choices. Quick Create remains accessible while dashboard counts load or fail.
- **Inventory → Receive Acquisition:** introduce purchased, gifted or otherwise acquired outside material using the existing universal acquisition workflow. New acquired lines can retain the selected acquisition origin. Inventory also owns standalone Add Strain management. Starting quantities do not represent current inventory balances.
- **Culture Library:** the photo-first strain catalog and reference drill-downs retain search, filters, all record kinds, FR derived strain information, lineage, provenance, photos, activity, edit and archive/restore. The primary creation/acquisition row is removed. Suitable physical source details offer a keyboard-accessible **Create From This** disclosure.
- **New Spore Print:** choose an active FR source and register an already completed collection through the existing 2B `POST /api/provenance/fruiting/{id}/collect` functionality. The resulting SP detail supports photographs. Source provenance and mixed-strain handling are preserved; collection creates no culture line or spawn consumption.
- Existing successful Establish Culture, Establish Tissue Clone, Create Isolate and ancestry correction remain on their source details. Manual grow-provenance registration remains under Cultivation and does not execute spawning.

## Source rules and navigation context

| Quick Create material | Available registered sources today | Execution in 2C.1 |
| --- | --- | --- |
| Agar plate | Active agar plate/slant, LC jar/syringe or spore material | Preparation/inoculation/transfer deferred |
| LC syringe | Active LC jar or syringe; LC containers recommended | Filling/transfer deferred |
| LC container / jar | Active agar plate/slant or LC jar/syringe | Preparation/inoculation deferred |
| Spawn jar / bag | Active agar plate/slant or LC jar/syringe | Preparation/inoculation deferred |
| Spore print | Active fruiting container | Register completed collection using 2B |
| Fruiting container | Active spawn jar/bag with explicit `ready` stage | Actual spawning/consumption deferred |

Active is a registration/archive status, **not proof of viability**. Physical-culture and spore quantities are initial measurements, so zero or unknown starting quantity is not used as a depleted-balance filter. No preparation, sterilization or viability state is invented. Colonizing/Used or archived spawn is excluded from future spawning choices. Unknown generic culture types are not assumed to be agar or LC. FR collection uses the current active-record semantics of the existing collection endpoint, without adding an invented fruiting readiness rule. Future lifecycle rules must extend source eligibility when implemented.

Options identify the source with permanent ID, material type, known strain(s), line and stage/status where present. FR identities preserve known/mixed/partial/unknown semantics. The selected source links back to its record. A source's kind and ID travel together in `?source_kind=physical&source_id=LC-0001` (or spores, spawn, fruiting). Destination screens load and validate available choices; missing, archived or incompatible preselection produces a visible error and no write. Loading, empty choices, failed requests and retry are explicit. URL context is not permission to create records.

Routine transfers will preserve an existing culture line; only a dedicated establishment should create a new one. Source selection in deferred entries performs GET requests only. These entries explain the future operation and contain **no Save/Create submit**, acquisition substitute, fabricated history or success message. Fruiting entry does not reuse manual grow provenance as an executed spawning operation.

## Canonical and legacy paths

| Old path | Redirect destination |
| --- | --- |
| `/culture-library/acquire` | `/inventory/receive-acquisition` |
| `/culture-library/receive-culture` | `/inventory/receive-culture` |
| `/culture-library/receive-spores` | `/inventory/receive-spores` |
| `/culture-library/add-strain` | `/inventory/strains/new` |
| `/culture-library/register-grow` | `/cultivation/register-grow` |

Redirects replace browser history and preserve query strings and hashes, including the existing strain/line acquisition context. Old APIs remain unchanged. Existing bookmarks, source record URLs and stored photographs continue to work.

## Explicit later-stage commitments

See [Roadmap](ROADMAP.md) for the approved 2C.2/2C.3 commitments. In particular, this increment does not introduce preparation batches, actual inoculation/transfers, inventory deductions, reusable pools, bulk creation, actual spawn consumption, substrate recipes, observations/contamination propagation or purchase tracking. The planned starting pool of 20 agar plates and six 6-quart shoebox trays is a future configuration requirement; it is **not seeded stock** in 2C.1.

## Validation

From the existing checkout:

```bash
(cd backend && ../.venv/bin/pytest -q)
(cd frontend && npm test && npm run build)
.venv/bin/python scripts/browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/lineage_browser_smoke.py /usr/bin/chromium
.venv/bin/python scripts/quick_create_browser_smoke.py /usr/bin/chromium
```

Browser scripts require optional Playwright and an installed Chromium. Each uses its own disposable database; none uses Debian data. The new smoke check exercises all six destinations, source filtering/preselection, Inventory and legacy navigation, uncluttered catalog, real spore collection, FR strain/provenance preservation, unchanged record counts for deferred entries, and desktop/mobile layouts. Screenshots are written to `/tmp/cultivatinator-quick-create-{desktop,mobile}.png`. Validation completed: **53 backend tests passed** (one existing upstream Starlette/AnyIO deprecation warning), **44 frontend tests passed** across five files, the TypeScript/Vite production build passed, and all three browser smoke scripts passed. The new browser flow produced no page errors and verified that deferred entries neither made write requests nor changed record counts.

Use the existing [stopped-container backup and rollback precautions](MILESTONE_2B.md#safe-debian-update--manual-after-review) before a separately authorized deployment. Do not overwrite live data or confuse the production data directory with the Git checkout or Compose configuration location.
