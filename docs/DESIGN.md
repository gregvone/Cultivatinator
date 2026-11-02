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
