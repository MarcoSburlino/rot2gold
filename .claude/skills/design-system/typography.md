# Typography

Three faces, bundled in `src/rot2gold/web/static/fonts/` as variable woff2 files (Latin subset, SIL Open Font License, licences beside them). The app never fetches fonts from the internet. Always give the fallbacks.

| Token | Stack | Use |
|---|---|---|
| `--font-display` | `"Outfit", "Avenir Next", system-ui, sans-serif` | Geometric sans matching the wordmark. Page titles, reading titles, video titles, note headings, dialog titles, the run page's Log/Details folds, the wordmark. Tight tracking. |
| `--font-ui` | `"Instrument Sans", "Helvetica Neue", system-ui, sans-serif` | Everything else: body, controls, lists, note text. |
| `--font-mono` | `"JetBrains Mono", ui-monospace, monospace` | Counts, dates, times, logs, paths, event dates. |

Scale (px): `--text-2xs` 11 · `--text-xs` 12 · `--text-sm` 13 · `--text-base` 15 · `--text-md` 18 · `--text-lg` 22 · `--text-xl` 28.

| Role | Face | Size | Weight | Line-height / tracking |
|---|---|---|---|---|
| Wordmark `Rot<b>2</b>Gold` (gold "2") | display | 20 sidebar, 18 top bar | 700 | 1, −0.035em |
| Page title (`h1`) | display | xl 28 | 600 | 1.15, −0.02em |
| Reading-pane title | display | lg 22 (26 from 768px) | 600 | 1.25, −0.015em |
| Video title | display | lg 22 (xl 28 from 768px) | 600 | 1.25, −0.02em |
| Note heading (`h2` in prose) | display | md 18 | 600 | 1.3 |
| List item title | ui | base 15 | 600 | 1.35 |
| Description in a reading pane | ui | md 18 | 400, text-1 | 1.55 |
| Body, note text | ui | base 15 | 400, text-2 | 1.6 |
| Metadata, help text | ui | sm 13 | 400, text-3 | 1.45 |
| Section label, rail title, table header | ui | 2xs 11 | 600, uppercase, 0.08em, text-3 | 1 |
| Status pill | ui | 2xs 11 | 600, uppercase, 0.05em | 1 |
| Counts, ids, times | mono | xs 12 | 400 | 1.4 |

Reading measure: rendered notes and descriptions max 68ch.
Numbers that line up (counts in lists and tables): `font-variant-numeric: tabular-nums`.
Tagline (brand moments only, not in the app's UI): 12–14px uppercase, 0.32em tracking.
