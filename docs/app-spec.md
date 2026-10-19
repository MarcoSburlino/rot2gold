# App spec

The app is the local UI for the `vn` pipeline in this repo. Marco adds a connection (for now, a TikTok collection) and presses **Extract**. The app then runs every step the pipeline runs today: sync, fetch, OCR and transcription, note writing, and an ideas pass. It also has screens for browsing posts, notes and ideas.

Other docs:

- The pipeline stages and their decisions: `spec.md`.
- Note writing: `note-writing.md`.
- The ideas pass: `ideas.md`.

The brain holds the knowledge. The app reads notes from it and writes notes to it, and never keeps its own copy.

**Status:** Phases 1–5 built (2026-10-19): connections, Extract, browsing, ideas, Settings, API backend, batch usage, undo, downloader updates and launcher. The phases are at the end.

## Goals

- **One click from URL to notes.** A collection URL becomes committed notes in the brain. The steps and output are the same as in the manual run of 2026-10-15.
- **Only new content.** Posts that were already processed are never downloaded or written up again.
- **Several connections.** A post saved in two collections is processed once and shown under both.
- **A specified ideas pass.** Ideas no longer depend on the judgement of each batch agent.
- **Screens** to browse connections, posts, notes and ideas.

Not goals: hosting, accounts, sync between devices, or mobile. The brain stays local and is never pushed.

## Constraints

- **Laptop only.** Fedora 44, GNOME on Wayland. Nothing assumes an always-on server. The app runs while Marco uses it. A run that is stopped or interrupted picks up again on the next Extract.
- **Local first.** yt-dlp, gallery-dl, ffmpeg, Tesseract and faster-whisper run on the laptop. The only network traffic is the downloads from the platform and the AI backend.
- **Slow downloads stay slow.** The pauses in `config.toml` (`[fetch]`) and in sync are kept, so the platform has no reason to block us.
- **Brain conventions.**
  - Unique file names with dashes, front matter, wikilinks.
  - `brain-index` and `brain-index --check` after every change.
  - Commits start with `agent: ` and stage only the paths the run changed. Never `git add -A`, never `.obsidian/`.
- **One run at a time.** A lock stops the app and a terminal `vn` command from running the pipeline together.

## Decisions

### One project

The pipeline and the app live in one repo, `~/Projects/video-notes-app` (Marco, 2026-10-19).

- Until 2026-10-19 the pipeline was its own project, `~/Projects/video-notes`. The folder was renamed, so its Git history and `data/` (database, media, Tesseract fallback) came along.
- **One of everything:** one venv, one database, one `AGENTS.md`, one CLI (`vn`).
- **Names kept:** the Python package stays `video_notes` and the CLI stays `vn`. The project name may still change, and these names don't need to follow it.

### Local web UI on 127.0.0.1:8740

`vn ui` starts a small web server and opens the browser at `http://127.0.0.1:8740`.

- **Stack:**
  - FastAPI and uvicorn, with HTML rendered on the server by Jinja2.
  - Plain HTML forms, plus a few lines of JavaScript for live run progress, which arrives over Server-Sent Events (SSE). Phase 1 needed nothing more, so htmx (planned) isn't used; add it, saved locally rather than from a CDN, only if a later screen needs it.
- **Why a web UI:**
  - It's the same Python as the pipeline, so the app calls the pipeline's functions directly.
  - There is no Node build step and nothing to package.
  - A desktop app (Tauri, Electron) would add Rust or Node toolchains and installers, for a single user. GTK would mean learning a UI toolkit.
- **Why 127.0.0.1:** it's the loopback address, reachable only from this laptop. Binding to `0.0.0.0` would expose the app to anyone on the same Wi-Fi.
- **Why 8740:** Marco's other projects use 3000, 3001, 5173, 1420/1421, 2020–2024, 3070, 5434, 8000, 8080, 8081, 8100 and 8888. 8740 is free. It's set in `config.toml` (`[app] port`) and noted in `AGENTS.md`.
- **No systemd service.** A service would run all the time on a laptop that is often asleep. The app starts on demand instead. `vn install-launcher` adds a GNOME `.desktop` entry. `vn ui` reuses an already running copy and writes output to `data/logs/ui.log` when started without a terminal.
- **Local request checks.** Every request must have the configured loopback Host header; writes must also have an Origin or Referer from that same local address. This blocks DNS rebinding and cross-site form posts.

### Functions, not printed output

The stages become functions that the app imports. The other option, wrapping the CLI, would mean parsing its printed output. That breaks on any change of wording, and it can't report structured errors.

- Each stage takes the ids it should work on and a `report(event)` callback, instead of printing.
- Stages raise typed errors (`errors.py`): `Blocked`, `CookiesNeeded`, `DownloaderOutdated`, `UsageLimit` and `LockHeld`. The CLI turns them into messages and exit codes. The UI turns them into banners that say what to do next.
- Every current `vn` command keeps working.

### A run is its own process

Extract starts `vn extract --conn <ids> --origin app` as a child process. The run writes its progress to SQLite (`run_events`), and the UI streams those rows to the browser over SSE.

- Closing the browser tab or restarting the server doesn't kill a run that may take an hour.
- A run started in a terminal (`vn extract`) shows up live in the UI the same way.
- There is one code path for both.

### Lock: flock on data/vn.lock

`flock` is a lock the Linux kernel keeps on an open file. Only one process can hold it, and the kernel releases it the moment that process exits, even after a crash or `kill -9`. So there is never a stale lock to clean up by hand.

- The holder writes `{pid, run_id, origin, started}` into the file. That way the other side can say who holds it: "a terminal run (pid 1234), started 10:02, is in progress".
- Who takes the lock:
  - `vn sync`, `fetch`, `process`, `run` and `extract` take it.
  - `status` and `pending` only read.
  - `done` and `skip` don't take it, because the note-writing agent calls them *during* a locked run.
- SQLite runs in WAL mode (write-ahead log) with a busy timeout, so the UI can read while a run writes.

### AI backend: claude -p, two ways to pay

Note writing and the ideas pass run as `claude -p` (Claude Code, non-interactive) in a child process. Marco picks the backend in Settings.

| | Subscription (default) | API key |
|---|---|---|
| Command | `claude -p …` | `claude -p …` |
| Auth | Marco's plan login (`claude auth status` → claude.ai, Pro) | `ANTHROPIC_API_KEY` from the keyring, set only in the child's environment |
| Billing | Plan usage limits, shared with claude.ai and interactive Claude Code | Pay per use |
| Safety | `ANTHROPIC_API_KEY` is removed from the child's environment, because Claude Code prefers a key over the plan login when both exist | `--max-budget-usd` per batch |

- **Why the same CLI for both:**
  - The agent loop, the tools (file edits, web search, `vn` commands) and the prompts are identical, so a note looks the same whichever backend wrote it.
  - Calling the Messages API directly would mean re-implementing the tools and web search.
  - The Agent SDK for Python runs this same CLI underneath, so the subprocess adds nothing.
  - API mode does not use `--bare`: bare mode removes WebSearch and WebFetch, which note writing needs. The key is supplied only to the child process, and a per-batch budget can cap spending.
- **Flags used for every call:**
  - `--output-format stream-json --verbose`: live events, and a final result with usage.
  - `--json-schema`: a structured report the app can check.
  - `--permission-prompts none`: nobody is there to answer prompts.
  - `--add-dir ~/Projects/brain`.
  - `--model` from settings.
  - Working directory: this repo.
- **Tools allowed:**
  - `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebSearch`, `WebFetch`.
  - `Bash(vn pending *)`, `Bash(vn done *)`, `Bash(vn skip *)`, `Bash(rg *)`, `Bash(find *)`.
  - No general shell and no git: the app commits, the AI doesn't.
- **What Anthropic's docs said on 2026-10-19:**
  - `claude -p` and the Agent SDK still draw from subscription limits. The planned separate credit was paused on 2026-06-15.
  - Since 2026-10-07, Max and Team plans also get monthly API credits. Pro doesn't.
  - The API key in the child environment selects API billing over the plan login.
  - Sources: support.claude.com articles 15036540 and 11145838, and code.claude.com/docs/en/headless.
- A Codex note-writing backend is deferred: a second agent backend would double the testing for this local app.

### Principle change: API keys allowed here

Marco's rule so far was "AI reasoning runs only through Marco's subscriptions, no API keys". **This project may also use an API key, if Marco chooses it in Settings.** The subscription stays the default.

The exception is for this project only. It is recorded here, in `AGENTS.md`, in `spec.md` and in the brain's `Projects/video-notes-app.md`. Marco's global rules don't change.

### API key in the GNOME keyring

The key is stored in the GNOME keyring with `secret-tool` (`/usr/bin/secret-tool`, attributes `service video-notes-app` and `account anthropic`). The keyring is an encrypted store that is unlocked when Marco logs in.

- **Why not a `chmod 600` file in `~/.config/`:**
  - The file would still be plain text on disk, visible to backups and `rg`.
  - Marco's rules already forbid agents from opening `api-key` files.
  - A keyring entry has no file to read by accident.
- **Entering the key:** the Settings page sends it to `secret-tool` on standard input, never as a command-line argument, because arguments are visible to every user in `ps`. Afterwards the page shows only "key set" or "not set".
- **No keyring:** without one (for example over SSH, with no desktop session), API mode stops with "keyring unavailable". It never falls back to a file.

### Review and undo after commits

Each batch of notes is committed on its own, and Git is the review and undo tool.

- **Review:** `git show` and Obsidian.
- **Undo:** an "Undo this run" button and `vn undo` revert a run's commits, re-open its noted posts if their note files are gone, and clear its ideas checks. Undo refuses staged or conflicting changes and is itself a locked, recorded run.

A true "hold before commit" mode would need a staging copy of `commonplace.md` and `quotes.md`, which every batch also edits. It is not built: undo provides review after the fact without a second commit path.

### Settings overlay

The tracked `config.toml` holds project defaults only. Editable preferences are validated and saved atomically in gitignored `data/settings.json`, then merged over defaults and `config.toml`. The API key stays in the GNOME keyring.

## Data model (schema v4)

All state stays in `data/vn.sqlite`.

### New tables

- `connections(id, platform, name UNIQUE, url, cookies_mode, firefox_profile, created_at, updated_at, last_synced_at, last_sync_source, last_error)`. `cookies_mode` is one of:
  - `auto`: anonymous first, then Firefox cookies;
  - `always`;
  - `never`.
- `connection_posts(connection_id, post_id, first_seen_at)`, primary key `(connection_id, post_id)`. This is the many-to-many link: a post in two collections is one `posts` row and two link rows.
- `connection_links(connection_id, url)`: post URLs pasted by hand, the fallback when listing fails. It replaces `data/links.txt`.
- `runs(id, origin, connection_ids, backend, model, started_at, finished_at, status, error, posts_listed, posts_fetched, posts_processed, posts_noted, posts_skipped, tokens_in, tokens_out, cache_read, cache_write, cost_estimate_usd, brain_commits)`.
- `run_events(run_id, ts, level, stage, post_id, message)`.
- Schema v3 adds `runs.kind` (`extract`, `ideas`, `ideas-dry-run`) and `runs.ideas_created`, `runs.ideas_updated`. Existing runs default to `extract`; v2→v3 is additive and needs no backup.
- Schema v4 adds `runs.undone_at` and `batches` (run, kind, ids, turns, duration, tokens, cost, five-hour usage, result). v3→v4 is additive and idempotent.

### Changes to `posts`

- `platform`, default `tiktok`.
  - TikTok ids stay bare, matching `post_id` in the existing notes.
  - Other platforms use `<platform>:<id>` (e.g. `yt:abc123`), so ids can't collide.
- `ideas_checked_at`: when the ideas pass last considered the post's note. NULL means it still has to.

### Status values

They stay `new → fetched → processed → done | skipped`, so existing rows and commands keep working. The UI labels them **listed, fetched, processed, noted, skipped**.

### Migration

It runs once, on the first start of the new code:

1. Copy `data/vn.sqlite` to `data/vn.sqlite.bak-v1`.
2. Add the new tables and columns.
3. Create the connection "Material" from `config.toml`'s `collection_url`, and link all existing posts to it.
4. Move the `meta.cookies` flag into that connection.
5. Remove `collection_url` from `config.toml`. From then on, connection URLs live only in the (gitignored) database.

`PRAGMA user_version` records the schema version. The plain `vn sync` command then syncs every connection.

### Deleting a connection

This removes the connection and its link rows. Posts, media and brain notes stay. The confirmation says how many posts belonged only to that connection.

## Sources (pluggable)

`src/video_notes/sources/base.py` defines what every platform provides:

- `platform`, `label` (shown in the platform picker), and `validate_url(url)`.
- `list_posts(connection) -> list[ListedPost]`, giving id, url, creator and upload date. It raises `CookiesNeeded` or `Blocked`.
- `detect_type(post)`: video or slideshow.
- `fetch(post, out_dir)`: writes the frame and audio, or the slide images.

`sources/tiktok.py` holds today's listing and download code. A registry (`{"tiktok": TikTokSource}`) fills the picker. OCR and transcription don't depend on the platform, so adding Instagram or YouTube later means one new file each.

## What Extract does

For the selected connections, `extract.py`:

1. **Lock.** Takes the lock, or fails with who holds it. Creates a `runs` row.
2. **Sync.** Lists each connection, adds new posts, links every listed post to the connection, and detects types for new posts.
3. **Fetch.** Downloads the `new` posts that belong to the selected connections, with the pauses and failure rules from `spec.md`.
4. **Process.** Runs OCR and transcription on their `fetched` posts.
5. **Write notes** for their `processed` posts, in batches (below). For each batch:
   1. Snapshot `git status --porcelain` in the brain.
   2. Run one `claude -p` with `prompts/write-notes.md` and the batch's ids.
   3. Check every post of the batch in the database: either `done` with a `note_path` that exists, or `skipped`.
   4. Run `brain-index`, then `brain-index --check`.
   5. Stage only the paths that changed since the snapshot *and* are under `Resources/commonplace/` or are generated indexes. Commit as `agent: video notes batch (run N)`. Anything else that changed (Obsidian, another agent) stays unstaged.
6. **Ideas pass.** Batches of up to 25 unchecked notes marked done on or after `[ideas] since`, with `prompts/ideas.md` (see `ideas.md`). Each completed batch is indexed, checked and committed from `Inbox/ideas/` and the indexes as `agent: ideas pass N (run N)`.
7. **Finish.** Totals the usage on the `runs` row and releases the lock.

Posts that belong to no selected connection are left alone, even if they are waiting.

### Batch sizes and usage

On 2026-10-15, each batch of 10 posts used 4–12 million cache-read tokens (about 1 million per note) and took 10–15 minutes. On Marco's Pro plan, the tenth batch hit the usage limit and waited about 5.5 hours. That shapes the defaults:

- **5 posts per batch.** The agent's context grows with every post, and every turn re-reads it, so tokens per post grow with batch length. Smaller batches start fresh more often.
- **At most 20 notes per Extract**, by default. The rest wait for the next Extract ("20 of 63 noted — run again").
- **Usage limit.** When `claude -p` reports a rate limit (a `rate_limit_event` whose status isn't `allowed`, three `api_retry` events with `error: rate_limit`, or an error result), the run stops cleanly with "Claude usage limit reached (resets HH:MM)". Everything finished so far is already committed.
- **Stop before the limit.** Every `claude -p` call reports the plan's usage in a `rate_limit_event`: the share of the 5-hour and 7-day windows already used, and when each resets. On the subscription, the run doesn't start another batch once the 5-hour window is 90% used (`config.toml` `[notes] stop_at_plan_usage`). The Run page shows both windows.
- **Usage shown.** Tokens and the cost estimate from each result event, per batch and per run.
  - On a subscription, the dollar figure is what the run would have cost on the API, not a charge.
  - The real remaining limit is at claude.ai → Settings → Usage.
- **Settings.** Batch size, notes per run and model are set in Settings and stored in `data/settings.json`.

### Stopping and interruptions

- **Stop** sends SIGINT, the polite "please stop" signal (like Ctrl+C). Downloads stop after the current post; `claude -p` ends its turn.
- Every pipeline stage already resumes where it stopped (`spec.md`).
- A note can be left half-written if the agent was stopped mid-post. So `note-writing.md` says: before writing, look for an existing note with the same `post_id`, and finish or replace it instead of creating `-2`.

### Download problems

- **Cookies needed.**
  - If anonymous listing fails and `cookies_mode` allows it, sync retries with Firefox cookies.
  - Firefox 158 keeps its profiles in `~/.config/mozilla/firefox/`. yt-dlp 2026.08 already looks there and picks the profile whose cookies were used last, so no setup is needed. A connection can name a profile folder (Edit → Firefox profile); `sources/firefox.py` lists them from `profiles.ini` for the Settings page.
  - If that fails too, the connection card says: open Firefox, log into TikTok, then Extract again.
- **Blocked or broken yt-dlp.**
  - Triggered by five failures in a row, or by a listing that fails in every mode.
  - A banner shows the installed yt-dlp version and how old it is, with an "Update downloaders" button.
  - The button runs `uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl`, shows its output, then offers Retry.
- **Manual fallback.** Each connection has a "Paste post URLs" box (one URL per line), used when listing fails.

## Screens

1. **Connections** (`/`)
   - One card per connection: platform, name, URL, post counts by status, last sync time and source, last error.
   - "Add connection": pick the platform, then a card asks for the URL and a name. The source validates the URL. Each card can be edited or deleted (with a confirmation).
   - Checkboxes and an **Extract** button. A run panel shows the stages, a live event log, AI usage so far, and a Stop button.
   - A banner whenever a run is active, including one started in a terminal.
2. **Videos** (`/videos`)
   - Every post, filtered by connection and status: creator, posted date, type, status, skip reason.
   - A post in several connections shows each one as a chip.
3. **Video detail** (`/videos/<id>`)
   - The note, rendered from its markdown file in the brain (`notefile.py`). Front matter is shown as a header, and `[[wikilinks]]` link to app pages where they resolve.
   - Rendering has raw HTML switched off: notes contain text from posts and the web, so `<script>` in a note shows as text and never runs.
   - The frame or slide images from `data/media/`.
   - **Open in Obsidian:** `obsidian://open?path=<absolute note path>`. This works without the vault name; the Flatpak Obsidian is registered for `obsidian://` links.
   - The raw OCR text and transcript, collapsed.
4. **Ideas** (`/ideas`)
   - Cards from `~/Projects/brain/Inbox/ideas/`, read from the files, so Marco's edits show up. Sorted by `support`, then `updated`, with status and text filters, source count, description and Obsidian link.
   - Each idea links its sources: video notes go to Video detail, other notes open in Obsidian.
   - The detail page renders the full idea safely. The rebuild form selects themes, an optional limit and a dry run (on by default); `/ideas/preview/<run_id>` renders its files.
5. **Runs** (`/runs`) and **Settings** (`/settings`)
   - Runs: the history with status, counts, usage per run and per batch, brain commits, and an Undo confirmation for eligible runs.
   - Settings: editable backend, models and batch limits; API key status, set, clear and test; plan usage, downloader versions and update; brain path, app address and Firefox profiles.

## Files

```
docs/app-spec.md           this file
docs/ideas.md              rules for the ideas pass
prompts/write-notes.md     prompt for one note-writing batch
prompts/ideas.md           prompt for the ideas pass
src/video_notes/
  db.py                    schema v4, migration, WAL                (changed)
  sync.py fetch.py process.py  ids, callbacks, typed errors        (changed)
  cli.py                   extract, ui, conn add|list|rm, lock      (changed)
  lock.py events.py errors.py
  extract.py               the Extract run
  runs.py                  shared lock, run row and final status
  notes.py                 note-writing batches
  ideas.py                 ideas pass; reading idea notes
  brain.py                 git snapshot, staged commit, brain-index, front matter, Obsidian links
  secrets.py               keyring access through secret-tool
  settings.py              validated preferences in data/settings.json
  undo.py                  safe git revert and queue restoration
  downloaders.py           installed versions and venv upgrade
  launcher.py              GNOME desktop entry and icon
  sources/                 base.py, tiktok.py
  ai/                      claude_cli.py
  notefile.py              reading notes (front matter, title) and rendering them with wikilinks
  web/                     app.py, templates/, static/
tests/
  test_core.py test_ideas.py  temporary database, brain and fake Claude checks
```

## Phases

0. **Docs.** This file, `ideas.md`, the prompts, the `note-writing.md` update, merging the pipeline and the app into one project.
1. **Core, Connections and Extract.**
   - Schema v2 and the migration, lock, events, sources, `extract.py`, the subscription backend, batch commits, `vn extract`.
   - A minimal UI: the Connections screen and the run panel.
   - Done when Marco adds a connection, presses Extract, and new posts become committed notes, as in the run of 2026-10-15.
2. **Browse.** The Videos and Video detail screens.
3. **Ideas.** The ideas pass in Extract, theme-based rebuilds, dry-run previews, and the Ideas screen. Migrating the 14 first-run idea files remains a separate brain change.
4. **API backend (built).** Settings, keyring, full Claude tool set, budget caps, usage per run and per batch.
5. **Extras (built).** Undo this run, a `.desktop` launcher, the Update downloaders button and Quit. Optional hold for review and a Codex note-writing backend are deferred for the reasons above.

## Acceptance checks

- The migration, run on a copy of the database, keeps all 104 posts (101 done, 3 skipped), every one linked to "Material".
- With a terminal `vn extract` running, Extract in the UI reports that run. After `kill -9` of the terminal run, the lock is free at once.
- A new post in Material is the only one fetched and written up. The brain commit contains only its note, the hub, quotes and the indexes. `.obsidian/graph.json` stays unstaged.
- A post saved in two connections is processed once and listed under both.
- With a wrong Firefox profile or a dead URL list, the UI shows the matching message and next step.
- Running the ideas pass twice on the same notes creates and updates nothing the second time.
- In API mode: `secret-tool lookup service video-notes-app account anthropic` finds the key, a batch reports its cost, and a missing key gives a clear error.
