# Components

Icons: inline SVG from `templates/_icons.html` (16px, 1.5px stroke, `currentColor`, `aria-hidden="true"`; buttons with only an icon carry `aria-label`). Set: plus, x, chevron, back, more (⋯), menu, external, calendar, check, stop, play, note, search, gear. A new glyph must match: 24 grid, 1.5 stroke, round caps and joins.

**Buttons.** Height 34 (sm 28), r-control. Primary: gold fill, `--on-accent` text, weight 600; on hover gold-strong plus `--glow-soft`. Use one per view. Secondary: `--surface-raised` fill, `--border-strong` border, cream text. Quiet: no border, text-2, hover `--hover`. Destructive: red text and a red outline, never filled. Pressed: 1px down. Disabled: 45% opacity. Label says exactly what happens ("Extract new videos", "Save settings", "Check for ideas").

**Focus.** Every interactive element: `outline: 2px solid var(--focus); outline-offset: 2px` on `:focus-visible`. Inputs instead get a gold border and a 3px soft gold ring while focused.

**Sidebar.** `--bg-sidebar`; sections separated by 24 spacing, not boxes.
- Brand: the wordmark `Rot<b>2</b>Gold` (display 20/700, gold "2").
- Nav row: icon-less text (text-2) + count (mono xs, text-3) right-aligned. The current page gets a `--hover` tint, cream text 600, a 3px glowing gold bar on the left, and its count in gold. Ideas, Learnings, Events, Videos, History.
- Section label: "Collections" (label style) + quiet icon button (plus).
- Connection row: name (link to its videos, 600) · more-button (⋯, opens its dialog). Line 2 (sm, text-2): "111 videos", plus "· 3 waiting for a note" in gold when some are. Line 3 (xs, text-3, links to the run): "Last extract yesterday: 7 notes, 0 ideas" / "nothing new"; failed or interrupted in alert. A failed listing shows the error in alert, 3 lines max, and an "Update downloaders" small button.
- Extract block: one primary button, full width, "Extract new videos" (all collections), with a hint below (xs text-3) saying what it does. No checkboxes, no options: per-collection extract lives in the collection's card. Hidden while a run is active (the live widget takes its place).
- Live run widget (only while running): sheet, gold-tinted border, `--glow-soft`, r-sheet; pulsing gold dot + what it's doing in words ("Extracting · process"); the latest log line (mono xs, one line, ellipsis); links "See progress" and "Stop".
- Footer: quiet gear button "Settings" · quiet "Quit".

**Filter chips.** Pill, sm 500, `--border-strong` border, no fill, text-2; count in mono 2xs after the label. Hover: `--hover`. Current: solid cream fill with dark text. Show a chip only when its group has items (no "Trying 0"); hide the row when only "All" is left. A removable filter ("In Material ×") is a gold-tinted chip with an x icon.

**Plain words.** Pipeline terms stay out of the main UI: "videos" not "posts", "History" not "runs", "waiting for a note" not "listed/fetched/processed", "What was said" not "transcript segments". Token counts, batches, run numbers and commit hashes live in a folded "Details".

**Folds.** Rarely needed controls go under a `<details>`: "Advanced" (sm text-2 summary) in forms and cards; "Log" and "Details" on a run page as `.disclosure` sections (hairline above, display md 600 title, chevron that turns when open). Open a fold by default only when its content matters now (a running log, an API backend that needs its key).

**Status pill.** Pill 20px, 2xs 600, uppercase, letter-spacing 0.05em, `--border-strong` border, text-3. "new"/"running": gold fill, dark text; "running" also has a pulsing dark dot. "failed"/"interrupted": red text and border. Labels: listed, fetched, processed, noted, skipped; new, trying, kept, dropped; ok, running, stopped, failed, interrupted.

**List row** (ideas, videos, runs). On one sheet (r-sheet), rows divided by hairlines, padding 14/16. Hover `--hover`. Selected: `--selected` background + a 3px glowing gold bar on the left. Video row: thumbnail 45×80 · title (600) + description (sm text-2, 2 lines clamp) + meta line (sm text-3: "@creator · 2026-10-14 · video") · status pill only when not noted. Idea row: title (ui 15/600, 2 lines) · source strip · description (2 lines) · status pill. History row: title (600) + one sentence of what it did (sm text-2) · relative time right, with a pill under it only when it didn't end ok.

**Source strip (signature).** A row of 9:16 thumbnails (r-xs, 1px border). In list rows: 27×48, overlapping by 6px like a fanned deck, each ringed 2px in the row's background so the edges read; plain images (the row is already a link — never put links inside links). In reading panes: 45×80, 4px apart, each a link to its video (title as `title`/`aria-label`). Max 6, then "+N" (mono) in a bordered tile. Next to it, the count "3 sources" (sm 500) with a 2px gold underline (`text-decoration: underline 2px var(--accent); text-underline-offset: 5px`). Sources that are not videos (brain notes) appear as a small bordered tile with a note glyph.

**Reading pane.** Sheet, r-sheet, padding 32 (16 mobile). Title (display), meta line, source strip, actions (Open in Obsidian primary · secondary links), the description (md, cream), then the rendered note at 68ch in text-2. Inside prose: `h2` display md 600 in cream, with 32 above / 8 below and no rule; lists 1.6 line-height; Obsidian callouts as an inset-black box with a 3px grey left border (not gold, to keep the accent rare); links underlined 1px grey, turning gold on hover.

**⋯ menu.** Rare or destructive actions on a page (e.g. Delete idea) sit behind a quiet ⋯ icon button at the top right of the reading pane, never beside the primary action. It opens a small raised list (r-control, border, `--shadow-menu`) aligned right; items sm, destructive items in alert and ending in "…" because they open a confirmation. Closes on a pick, an outside click or Escape.

**Dialog card.** `<dialog>`, sheet, r-sheet, `--shadow`, width min(560px, 100vw − 32px) (small 420, wide 720), padding 24; header (display md 600 + close icon button), body (sm text-2), footer with actions right-aligned (primary last). Backdrop `--scrim` with a 6px blur. Escape and the close button close it.

**Tabs (Settings card).** The card has a fixed height (min(720px, viewport − 32)) so switching tabs never resizes it; the tab row is sticky and only the panel scrolls. A row of quiet buttons with `role="tab"`; current has cream text and a 2px gold underline; arrow keys, Home and End move between tabs. Panels `role="tabpanel"`. A Settings form's result appears inside the reopened card, never as a page banner.

**Banner.** Full width in the main area, r-control, padding 12/16, sm text. Info: sheet + border. Error: alert-soft + red text. Action banner: `--accent-soft` with a gold-tinted border and a 3px gold left mark, one sentence and one small button ("1 older note hasn't been checked for ideas yet. [Check them]").

**Run summary.** The first line of a run page: one sentence, md text ("Checked 111 videos, wrote 7 notes, no new ideas."). While running it becomes the live log line (mono sm text-3) under the stages. Stages are pills: done ones carry a gold check, the current one a pulsing gold dot and a soft glow.

**Empty state.** One sentence that invites the next action, plus at most one button. text-2, no illustration.

**Tables** (batches, runs): sm text, mono for numbers (tabular), header row 2xs uppercase text-3 on inset black, hairline rows, no zebra stripes. The run log is mono xs on inset black. Usage meters fill from ember to gold.

**Phone drawer** (< 768 px). The sidebar becomes a drawer opened from a top bar's Menu button; a scrim covers the page, the page behind is `inert`, Escape or the × closes it and focus returns to Menu. Opening a dialog from the drawer closes the drawer first.

**Scrollbars.** Thin, text-3 at 45% on a transparent track (Firefox otherwise paints some white in dark mode).
