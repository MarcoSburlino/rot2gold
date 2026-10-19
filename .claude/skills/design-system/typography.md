# Typography

Three faces, all installed on Marco's Fedora laptop: no downloads, works offline. Always give the fallbacks.

| Token | Stack | Use |
|---|---|---|
| `--font-title` | `"C059", "Noto Serif", Georgia, serif` | URW Century Schoolbook, a textbook face. Only for: page titles, idea titles, video titles, section heads (`h2`) inside a rendered note. Never for UI controls or body text. |
| `--font-ui` | `"Adwaita Sans", "Cantarell", "Noto Sans", system-ui, sans-serif` | GNOME's own UI face. Everything else: body, controls, lists, note body text. |
| `--font-mono` | `"Adwaita Mono", "Source Code Pro", monospace` | Ids, timestamps, counts in tables, run logs, paths. |

Scale (px; rem at 16px root): `--text-xs` 12 · `--text-sm` 13 · `--text-base` 15 · `--text-md` 18 · `--text-lg` 22 · `--text-xl` 28.

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| Page title (`h1`) | title | xl 28 | 400 (C059 Roman reads strong already) | 1.2 |
| Idea / video title in a reading pane | title | lg 22 | 400 | 1.25 |
| Note section head (`h2` in prose) | title | md 18 | 700 | 1.3 |
| List item title | ui | base 15 | 600 | 1.35 |
| Body, note text | ui | base 15 | 400 | 1.6 |
| Metadata, help text | ui | sm 13 | 400, graphite | 1.45 |
| Sidebar section label | ui | xs 12 | 600, uppercase, letter-spacing 0.06em, graphite | 1 |
| Counts, ids, times | mono | xs 12 / sm 13 | 400 | 1.4 |

Reading measure: rendered notes and idea bodies max 68ch.
Numbers that line up (counts in lists and tables): `font-variant-numeric: tabular-nums`.
