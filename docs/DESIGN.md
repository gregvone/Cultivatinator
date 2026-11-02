# Industrial Monitoring Console

A purpose-built laboratory and cultivation workspace: graphite/charcoal surfaces, restrained steel-blue emphasis, subtle borders, readable status information, and compact comfortable panels. No fabricated activity or decorative charts fill the empty application.

## Tokens and typography

- Background `#111923`, sidebar `#151E2B`, panels `#1B2837` / `#202D3D`, secondary `#263548`.
- Accent `#65AEEF`, primary text `#EDF3FA`, secondary text `#9AAEC5`.
- Muted green `#83B6A2`, amber `#DDBF83`, red `#E8AAA5`. Status must also have a text label, never color alone.
- Local system sans-serif stack (Inter if installed, Segoe UI, system-ui); no remote font dependency. Headings use moderate weight; small uppercase labels provide hierarchy.
- Shared CSS in `frontend/src/styles.css` uses Tailwind 4 and reusable console classes; spacing generally follows 4/8px increments.

## Navigation and hierarchy

Fixed desktop sidebar: Dashboard, Culture Library, Laboratory, Cultivation, Inventory, Reports, Settings. Active routes have text/background/border indicators. Header provides section context and room for future real actions. Dashboard defaults to four API-backed counts, followed by attention and conditions, active cultivation, and recent activity. Growing Cultures is prominent in Laboratory. Future capabilities are labeled planned and presented without nonfunctional buttons.

## Reusable conventions

Shell, PageHeader, Panel, EmptyState, LoadingState and ErrorState keep page behavior consistent. Lucide icons have consistent stroke and scale; decorative icons are hidden from assistive technology. Errors are announced and have an actual retry control; loading is announced; navigation and forms use native semantic controls. Focus indicators and a skip link support keyboard use.

Desktop-first with four summary columns and two panel columns, narrowing to two summary columns and one panel column. Below 800px the sidebar becomes a toggleable menu, with a close backdrop and route-selection dismissal. Feature lists collapse to one column on phones. Avoid excessive animations and large empty decorative areas. Review changes at desktop and mobile widths, including long text and error states.

## Culture Library — Milestone 2A

The landing view is a responsive strain photo-card grid with uniform 4:3 cover crops and a Lucide DNA placeholder. Cards contain name, optional scientific reference, immutable ID, status, and related totals. Add Strain, Receive Culture and Receive Spores are real primary actions. Search, status and appropriate per-view filters sit above records; secondary tabs expose lines, spores and individual containers. Empty results contain no sample data and offer a working Add Strain action.

Guided registration uses strain → line → optional material → review (spores use a separate three-step flow). New strains are held inline until the whole acquisition saves; Back preserves values. Unknown strain and quantity are explicit states. The browser supplies today's local acquisition date, with correction/clearing allowed. Descriptive editing leaves lineage relationships intact. Starting/Registered Quantity labels never imply a live balance. Record details link to related records, provide archive/restore, and list timestamped history.

Photo galleries accept multiple files after creation; covers, full-image modal viewing (Escape closes, native dialog focus management), and confirmed removal work for every record kind. Archive confirmation explicitly states that relationships and photos remain. Native labeled fields, field errors, busy controls, success/error messages, keyboard focus indicators, and wrapping grids/forms preserve accessibility and mobile usability.

## Lineage and grow provenance — Milestone 2B

Keep the strain card grid as the primary Culture Library view. Secondary tabs expose Spawn Jars & Bags, Grow Batches and Fruiting Containers. Receive Acquisition offers all supported entry stages with explicit unknown strain, optional acquisition information, and a review/back step. Grow registration shows source checkboxes, shared/specific allocation and individually editable containers; mixed lines and mixed named strains have separate text warnings. Cultivation links to these implemented foundations while describing preparation, consumption and harvest as future work.

Detail pages show compact relationship lists with distinct labels for confirmed parents, possible parents, documented physical sources and batch membership. Source links include permanent identities and archive state. Establish Culture, Establish Tissue Clone, Create Isolate and Collect Spores live on their actual source records; optional initial material reuses physical-culture registration. Ancestry correction requires a reason and displays current candidates. History retains previous choices. New records use the existing photo gallery and archive UI. Manual provenance explicitly states that it is not a consumption event; no automatic Used status, fake Mixed strain or hybrid assertion is shown. Native labels, busy/error/retry states, keyboard operation and wrapping panels preserve desktop/mobile usability.

## Milestone 2C.1 responsibility split

Dashboard Quick Create provides six compact icon links near the bottom in a three/two/one-column responsive grid. Each opens a material-specific source screen, with full source IDs and registered identity, appropriate active-record/type filters, optional URL preselection, loading/retry and unavailable-source errors. Physical-source details offer a native Create From This disclosure; only compatible destinations appear. Selected sources link back to their records. No viability or remaining stock is inferred from initial quantities.

Inventory owns universal outside acquisition and standalone strain management. Culture Library removes its crowded creation row and keeps the photo-first catalog, filters, reference records, lineage/provenance and existing maintenance controls. Old creation URLs redirect with query/hash context preserved. Global milestone labels now identify 2C.1. Only completed spore-print collection executes an existing operation from Quick Create; future transfer/inoculation/spawning entries clearly describe unavailable steps and have no fake submit button. [2C.1 details](MILESTONE_2C1.md).

## Milestone 2C.2 operational interface

Quick Create agar/LC/spawn entries only inoculate prepared material (Fill for syringes), with ready counts, partial selections and source preselection. Inventory owns generic Add Inventory, Stock & Pools, Prepared Materials → Prepare Materials and Transactions. Recipes has its own main-navigation workspace, including variant comparison and substrate definitions. No opening quantities or example stock are prefilled. Known/unknown balances, unit-bearing actual recipe scaling, free reusable count, per-container/total usage, readiness, expiry warnings, errors and stable retries are visible. New preparations save Ready to Inoculate automatically; historical Preparing records retain their explicit readiness action. Ready for Spawning remains separate; terminal/depleted sources disappear from choices. Bulk/partial selections keep individual permanent IDs and session links. Record details show lifecycle, balance and exact physical source/destinations separately from genetic lineage, plus reasoned Complete/Failed controls and existing galleries. Spore-inoculated plates offer an explicit successful-establishment action rather than fabricating a shared culture line. Fruiting/spawning remains visibly deferred; no FR preparation shortcut simulates consumption.
