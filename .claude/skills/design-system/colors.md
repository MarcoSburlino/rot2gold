# Colours

Six colours. Defined once as CSS custom properties on `:root`, redefined under `@media (prefers-color-scheme: dark)`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--paper` | `#F5F6F3` | `#121417` | App background, sidebar background. A cool off-white, deliberately not cream. |
| `--sheet` | `#FFFFFF` | `#1A1D21` | Reading surfaces: the list, the reading pane, dialogs, inputs. |
| `--ink` | `#1E2329` | `#E7E8E4` | Text, primary buttons (ink fill, sheet text), focus ring. |
| `--graphite` | `#646B73` | `#9AA0A6` | Secondary text, metadata, icons at rest. |
| `--rule` | `#DFE1DC` | `#2C3036` | Hairlines (1px), borders of controls and sheets. |
| `--highlighter` | `#F2D53C` | `#E6C832` | The only accent. Used like a marker pen: the underline under a support count, the selected list row's left mark, the active run dot, the "new" status pill, the current nav item's mark. Text on it is always `--on-highlighter`. Never a button fill, never large areas. |
| `--on-highlighter` | `#1E2329` | `#121417` | Text on highlighter. |
| `--alert` | `#B3261E` | `#F28B82` | Errors and destructive actions only (Delete, Undo confirm, failed run). |

Derived (computed in CSS with `color-mix`, not new colours):
- `--hover`: `color-mix(in srgb, var(--ink) 5%, transparent)` — row and button hover.
- `--selected`: `color-mix(in srgb, var(--highlighter) 18%, var(--sheet))` — selected list row background.
- `--alert-soft`: `color-mix(in srgb, var(--alert) 10%, var(--sheet))` — error banner background.

Contrast (WCAG): ink/paper 14.6, graphite/paper 5.0, graphite/sheet 5.4, ink/highlighter 10.8, alert/sheet 6.5; dark: 15.0, 6.4, 11.1, 7.1. All pass AA for body text.

Status colours: there is no green/orange/red traffic-light set. Status pills are neutral outlines; meaning comes from the word, plus the highlighter for "new"/"running" and alert for "failed".
