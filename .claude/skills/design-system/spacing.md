# Spacing and layout

Scale (4px base): `--s-1` 4 · `--s-2` 8 · `--s-3` 12 · `--s-4` 16 · `--s-5` 24 · `--s-6` 32 · `--s-7` 48.
- Inside a component (icon to label, chip padding): 4–8.
- Between items in a list or form fields: 12–16.
- Between sections of a page: 32. Page padding: 32 desktop, 16 mobile.
Radii: `--r-control` 6 (buttons, inputs, chips, thumbnails), `--r-sheet` 10 (sheets, dialogs). Pills (status, counts): 999.
Borders: 1px `--rule`. Shadow: only dialogs, `0 12px 40px rgb(0 0 0 / 0.18)` (dark: 0.5).

Layout:
- App shell: CSS grid `288px 1fr`. Sidebar is sticky, full viewport height, scrolls on its own, background `--paper`, right hairline. Main area background `--paper`, content on `--sheet`.
- Main content max width 1200px; reading columns 68ch.
- Ideas page: from 1100px, master-detail grid `minmax(320px, 400px) 1fr`; both panes are sheets; the list pane scrolls independently (`max-height: calc(100vh - header)`).
- Video detail: from 1000px, `1fr 300px` (reading column + right rail).

Breakpoints: mobile < 768px (sidebar becomes a top bar + drawer; single column), tablet 768–1099px (sidebar stays; master-detail collapses to list → detail pages), desktop ≥ 1100px.
Thumbnails: always 9:16 (`aspect-ratio: 9 / 16; object-fit: cover`). Sizes: strip 27×48, list row 45×80, video header 90×160, rail full width.
