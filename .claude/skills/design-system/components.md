# Components

Icons: inline SVG from `templates/_icons.html` (16px, 1.5px stroke, `currentColor`, `aria-hidden="true"`; buttons with only an icon carry `aria-label`). Set: gear, plus, more (⋯), play, stop, external, check, x, chevron.

**Buttons.** Height 32 (sm 28). Primary: ink fill, sheet text, weight 600. Secondary: sheet fill, rule border, ink text. Quiet: no border, graphite text, hover `--hover`. Destructive: alert text and border (alert fill only inside the confirm dialog). Disabled: 45% opacity. Label says exactly what happens ("Extract new videos", "Save settings", "Check for ideas").

**Focus.** Every interactive element: `outline: 2px solid var(--ink); outline-offset: 2px` on `:focus-visible`.

**Sidebar.** Paper background; sections separated by 24 spacing, not boxes.
- Brand: app name, ui 15/600.
- Nav row: icon-less text + count (mono xs, graphite) right-aligned; current page marked by a 3px highlighter bar on the left and ink text 600. Ideas, Videos, History.
- Section label: "Collections" (label style) + quiet icon button (plus).
- Connection row: name (link to its videos, 600) · more-button (⋯, opens its dialog). Line 2 (sm, graphite): "111 videos", plus "· 3 waiting for a note" marked with a soft highlighter stroke when some are. Line 3 (xs, graphite, links to the run): "Last extract yesterday: 7 notes, 0 ideas" / "nothing new"; failed or interrupted in alert. A failed listing shows the error in alert, 3 lines max, and an "Update downloaders" small button.
- Extract block: one primary button, full width, "Extract new videos" (all collections), with a hint below (xs graphite) saying what it does. No checkboxes, no options: per-collection extract lives in the collection's card. Hidden while a run is active (the live widget takes its place).
- Live run widget (only while running): sheet, rule border, r-sheet; pulsing highlighter dot + what it's doing in words ("Extracting · process"); the latest log line (mono xs, one line, ellipsis); links "See progress" and "Stop".
- Footer: quiet gear button "Settings" · quiet "Quit".

**Filter chips.** Pill, sm text, rule border, sheet fill; count in mono after the label. Current: ink fill, sheet text. Show a chip only when its group has items (no "Trying 0"); hide the row when only "All" is left. A removable filter ("In Material ×") is a chip with an x link.

**Plain words.** Pipeline terms stay out of the main UI: "videos" not "posts", "History" not "runs", "waiting for a note" not "listed/fetched/processed", "What was said" not "transcript segments". Token counts, batches, run numbers and commit hashes live in a folded "Details".

**Folds.** Rarely needed controls go under a `<details>`: "Advanced" (sm graphite summary) in forms and cards; "Log" and "Details" on a run page as `.disclosure` sections (hairline above, chevron that turns when open). Open a fold by default only when its content matters now (a running log, an API backend that needs its key).

**Status pill.** Pill, xs 600, uppercase, letter-spacing 0.04em, rule border, graphite text. "new"/"running": highlighter fill, on-highlighter text. "failed": alert text and border. Labels: listed, fetched, processed, noted, skipped; new, trying, kept, dropped; ok, running, stopped, failed, interrupted.

**List row** (ideas, videos, runs). On a sheet, rows divided by hairlines, padding 12/16. Hover `--hover`. Selected: `--selected` background + 3px highlighter left mark. Video row: thumbnail 45×80 · title (600) + description (sm graphite, 2 lines clamp) + meta line (sm graphite: "@creator · 2026-10-14 · video") · status pill only when not noted. Idea row: title (ui 15/600, 2 lines) · source strip · description (2 lines) · status pill. History row: title (600) + one sentence of what it did (sm graphite) · relative time right, with a pill under it only when it didn't end ok.

**Source strip (signature).** A row of 9:16 thumbnails (r-control, 1px rule border). In list rows: 27×48, overlapping by 6px like a fanned deck, each ringed 2px in the row's background so the edges read; plain images (the row is already a link — never put links inside links). In reading panes: 45×80, 4px apart, each a link to its video (title as `title`/`aria-label`). Max 6, then "+N" in a rule-bordered tile. Next to it, the count "3 sources" with a 3px highlighter underline (`text-decoration: underline 3px var(--highlighter); text-underline-offset: 3px`). Sources that are not videos (brain notes) appear as a small rule-bordered tile with a note glyph.

**Reading pane.** Sheet, r-sheet, padding 32 (16 mobile). Title (title lg), meta line, source strip, actions (Open in Obsidian primary · secondary links), then the rendered note at 68ch. Inside prose: `h2` title md 700 with 32 above / 8 below and no rule; lists 1.6 line-height; Obsidian callouts as a sheet-on-paper box with a 3px ink left border (not highlighter, to keep the accent rare); links ink with underline 1px graphite.

**⋯ menu.** Rare or destructive actions on a page (e.g. Delete idea) sit behind a quiet ⋯ icon button at the top right of the reading pane, never beside the primary action. It opens a small sheet list (r-control, rule border, shadow) aligned right; items sm, destructive items in alert and ending in "…" because they open a confirmation. Closes on a pick, an outside click or Escape.

**Dialog card.** `<dialog>`, sheet, r-sheet, shadow, width min(560px, 100vw − 32px), padding 24; header (title md 600 + close icon button), body, footer with actions right-aligned (primary last). Backdrop `rgb(0 0 0 / 0.35)`. Escape and the close button close it.

**Tabs (Settings card).** The card has a fixed height (min(720px, viewport − 32)) so switching tabs never resizes it; the tab row is sticky and only the panel scrolls. A row of quiet buttons with `role="tab"`; current has ink text and a 2px ink underline; arrow keys, Home and End move between tabs. Panels `role="tabpanel"`. A Settings form's result appears inside the reopened card, never as a page banner.

**Banner.** Full width in the main area, r-control, padding 12/16, sm text. Info: sheet + rule border. Error: alert-soft + alert text. Action banner: info banner with a highlighter left mark, one sentence and one small button ("1 older note hasn't been checked for ideas yet. [Check them]").

**Run summary.** The first line of a run page: one sentence, md text ("Checked 111 videos, wrote 7 notes, no new ideas."). While running it becomes the live log line (mono sm graphite) under the stages.

**Empty state.** One sentence that invites the next action, plus at most one button. Graphite text, no illustration.

**Tables** (batches, runs): sm text, mono for numbers (tabular), header row xs uppercase graphite, hairline rows, no zebra stripes.

**Phone drawer** (< 768 px). The sidebar becomes a drawer opened from a top bar's Menu button; a scrim covers the page, the page behind is `inert`, Escape or the × closes it and focus returns to Menu. Opening a dialog from the drawer closes the drawer first.

**Scrollbars.** Thin, graphite at 45% on a transparent track, in both themes (Firefox otherwise paints some white in dark mode).
