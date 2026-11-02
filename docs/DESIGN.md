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
