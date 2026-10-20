# Spacing and layout

Scale (4px base): `--s-1` 4 · `--s-2` 8 · `--s-3` 12 · `--s-4` 16 · `--s-5` 24 · `--s-6` 32 · `--s-7` 48.
- Inside a component (icon to label, chip padding): 4–8.
- Between items in a list or form fields: 12–16.
- Between sections of a page: 24–32. Page padding: 32 desktop, 16 mobile.

Radii:
- `--r-xs` 4: thumbnails, menu items;
- `--r-control` 8: buttons, inputs, banners, tables, the log;
- `--r-sheet` 14: sheets, dialogs, the live widget;
- 999: chips, pills, the search field.

Controls are 34px high (`--control`), small ones 28 (`--control-small`).
Borders: 1px everywhere. Shadows: only dialogs (`--shadow`) and ⋯ menus (`--shadow-menu`).

Layout:
- **App shell:** CSS grid `288px 1fr`. The sidebar is sticky, full height, scrolls on its own, on `--bg-sidebar` with a right hairline. The main area is on `--bg-app`, with content on sheets.
- **Main content:** max width 1320px; reading columns 68ch.
- **Ideas, Learnings and Events:** from 1100px, master-detail `minmax(320px, 380px) 1fr`. Both panes are sheets, and the list pane scrolls on its own.
- **Video detail:** from 1000px, `1fr 300px`. The reading sheet sits beside a rail whose sections are divided by hairlines, not boxed.

Breakpoints:
- **Phone (< 768px):** top bar plus drawer; single column.
- **Tablet (768–1099px):** the sidebar stays; master-detail becomes list → detail pages.
- **Desktop (≥ 1100px).**

Thumbnails are always 9:16 (`aspect-ratio: 9 / 16; object-fit: cover`). Sizes: strip 27×48, list row 45×80, video header 90×160 (72 on phones), rail full width.
