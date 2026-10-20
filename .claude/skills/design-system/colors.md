# Colours

Dark only. Defined once as CSS custom properties on `:root` in `style.css`; `color-scheme: dark`.

| Token | Value | Use |
|---|---|---|
| `--bg-app` | `#0C0C0D` | Page background. |
| `--bg-sidebar` | `#090809` | Sidebar and phone top bar: the darkest black. |
| `--surface-sheet` | `#141415` | Sheets: lists, reading pane, dialogs, tables. One step lighter than the page. |
| `--surface-raised` | `#19191B` | Secondary buttons, ⋯ menus. |
| `--surface-inset` | `#090809` | Inputs, thumbnails, the run log, callouts, code. |
| `--text-1` | `#F9F4EF` | Cream. Text, titles. |
| `--text-2` | `#B5B0A9` | Warm grey. Descriptions, note body, ledes. |
| `--text-3` | `#8E8A85` | Warm grey. Metadata, help text, icons at rest. |
| `--border` | `#2A2A2D` | Hairlines (1px) of sheets and rows. |
| `--border-strong` | `#3A3A3E` | Borders of controls: buttons, inputs, chips, pills. |
| `--accent` | `#F8AD45` | **The gold**, the "2" in the wordmark. Used like light: the current nav bar, the selected row's bar, the open tab's underline, the running dot, "new" pills, the primary button, the "N sources" underline, upcoming event dates, counts that need attention. Text on it is `--on-accent`. |
| `--accent-strong` | `#FBC77A` | Primary button hover. |
| `--on-accent` | `#090809` | Text on gold. |
| `--ember` | `#7D542C` | Only the start of the usage meter's gradient. |
| `--alert` | `#FF7A6B` | Errors and destructive actions only. |
| `--focus` | `#FBC77A` | Focus outline. |

Derived (with `color-mix`, not new colours):
- `--hover`: cream at 6% (rows, quiet buttons, nav);
- `--selected`: gold at 10% on the sheet (selected row);
- `--accent-soft`: gold at 14% on the sheet (action banners, filter chips);
- `--alert-soft`: red at 12% on the sheet (error banners);
- `--scrim`: black at 60% (dialogs, the phone drawer).

Glows instead of shadows:
- `--glow-dot` (10px gold) on gold marks;
- `--glow-soft` (18px gold at 22%) on primary button hover, the live-run widget and the current run stage.

Contrast on the sheet (`#141415`): text-1 16.8, text-2 8.5, text-3 5.4, gold 9.7, alert 7.2; dark text on gold 10.5. All pass AA for body text.

Status: there is no green/amber/red set. Pills are neutral outlines. Meaning comes from the word, plus gold for "new"/"running" and red for "failed".
