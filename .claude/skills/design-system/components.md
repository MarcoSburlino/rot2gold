# Components

Icons: inline SVG from `templates/_icons.html` (16px, 1.5px stroke, `currentColor`, `aria-hidden="true"`; buttons with only an icon carry `aria-label`). Set: gear, plus, more (⋯), play, stop, external, check, x, chevron.

**Buttons.** Height 32 (sm 28). Primary: ink fill, sheet text, weight 600. Secondary: sheet fill, rule border, ink text. Quiet: no border, graphite text, hover `--hover`. Destructive: alert text and border (alert fill only inside the confirm dialog). Disabled: 45% opacity. Label says exactly what happens ("Extract 2 collections", "Save settings", "Apply 9 ideas to the brain").

**Focus.** Every interactive element: `outline: 2px solid var(--ink); outline-offset: 2px` on `:focus-visible`.

**Sidebar.** Paper background; sections separated by 24 spacing, not boxes.
- Brand: app name, ui 15/600.
- Nav row: icon-less text + count (mono xs, graphite) right-aligned; current page marked by a 3px highlighter bar on the left and ink text 600.
- Section label: "Collections" (label style) + quiet icon button (plus).
- Connection row: checkbox · name (link to its videos, 600) · more-button (⋯, opens its dialog). Line 2 (sm, graphite): "111 posts · 0 waiting". Line 3 (xs): last run — status mark (✓ ok, ● running in highlighter, ! failed in alert, ■ stopped) · relative time · "7 noted · 2 ideas", the whole line links to the run. A failed listing shows the error in alert, 2 lines max.
- Extract block: primary button, full width, label follows the checkboxes ("Select a collection" disabled · "Extract Material" · "Extract 2 collections"); a quiet ▾ button opens a popover (details/summary) with Write notes, Find ideas, Max notes.
- Live run widget (only while running): sheet, rule border, r-sheet; pulsing highlighter dot + "Run 5 · process"; the latest log line (mono xs, one line, ellipsis); links "Log" and "Stop".
- Footer: quiet gear button "Settings" · quiet "Quit".

**Filter chips.** Pill, sm text, rule border, sheet fill; count in mono after the label. Current: ink fill, sheet text. A removable filter ("In Material ×") is a chip with an x link.

**Status pill.** Pill, xs 600, uppercase, letter-spacing 0.04em, rule border, graphite text. "new"/"running": highlighter fill, on-highlighter text. "failed": alert text and border. Labels: listed, fetched, processed, noted, skipped; new, trying, kept, dropped; ok, running, stopped, failed, interrupted.

**List row** (ideas, videos, runs). On a sheet, rows divided by hairlines, padding 12/16. Hover `--hover`. Selected: `--selected` background + 3px highlighter left mark. Video row: thumbnail 45×80 · title (600) + description (sm graphite, 2 lines clamp) + meta line (sm graphite: "@creator · 2026-10-14 · video") · status pill right. Idea row: title (ui 15/600, 2 lines) · source strip · meta ("3 sources · updated 19 Oct") · status pill.

**Source strip (signature).** A row of 9:16 thumbnails (27×48, r-control, 1px rule border), overlapping by 6px like a fanned deck in lists, spaced 4px apart in reading panes; max 6 then "+N" in a rule-bordered tile. Each is a link to the video with the video title as `title`/`aria-label`. Next to it, the count "3 sources" with a 3px highlighter underline (`text-decoration: underline 3px var(--highlighter); text-underline-offset: 3px`). Sources that are not videos (brain notes) appear as a small rule-bordered tile with a note glyph.

**Reading pane.** Sheet, r-sheet, padding 32 (16 mobile). Title (title lg), meta line, source strip, actions (Open in Obsidian primary · secondary links), then the rendered note at 68ch. Inside prose: `h2` title md 700 with 32 above / 8 below and no rule; lists 1.6 line-height; Obsidian callouts as a sheet-on-paper box with a 3px ink left border (not highlighter, to keep the accent rare); links ink with underline 1px graphite.

**Dialog card.** `<dialog>`, sheet, r-sheet, shadow, width min(560px, 100vw − 32px), padding 24; header (title md 600 + close icon button), body, footer with actions right-aligned (primary last). Backdrop `rgb(0 0 0 / 0.35)`. Escape and the close button close it.

**Tabs (Settings card).** A row of quiet buttons with `role="tab"`; current has ink text and a 2px ink underline. Panels `role="tabpanel"`.

**Banner.** Full width in the main area, r-control, padding 12/16, sm text. Info: sheet + rule border. Error: alert-soft + alert text. Pending dry run: info banner with a highlighter left mark and a "Review" link.

**Empty state.** One sentence that invites the next action, plus at most one button. Graphite text, no illustration.

**Tables** (batches, runs): sm text, mono for numbers (tabular), header row xs uppercase graphite, hairline rows, no zebra stripes.
