# App spec

> **About this document:** a design log, written while Rot2Gold was built for its author's own vault, so it mentions his setup (his brain at `~/Projects/brain`, its folders, Fedora, his collection). Since 2026-10-21 those are settings anyone can choose (`src/rot2gold/resources/defaults.toml`, the first-run setup). The [README](../README.md) describes the app for everyone.

The app is the local UI for the `r2g` pipeline in this repo. Marco adds a connection (for now, a TikTok collection) and presses **Extract**. The app then runs every step the pipeline runs today: sync, fetch, OCR and transcription, note writing, and a pass that finds ideas, learnings and events. It also has screens for browsing posts, notes, ideas, learnings and events.

Other docs:

- The pipeline stages and their decisions: `spec.md`.
- Note writing: `note-writing.md`.
- The ideas, learnings and events pass: `ideas.md`.

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
- **One run at a time.** A lock stops the app and a terminal `r2g` command from running the pipeline together.

## Decisions

### One project

The pipeline and the app live in one repo, `~/Projects/rot2gold` (Marco, 2026-10-19).

- Until 2026-10-19 the pipeline was its own project, `~/Projects/video-notes`. The folder was renamed (`~/Projects/video-notes-app`, then `~/Projects/rot2gold`), so its Git history and `data/` (database, media, Tesseract fallback) came along.
- **One of everything:** one venv, one database, one `AGENTS.md`, one CLI (`r2g`).
- **Names:** Marco named the app **Rot2Gold** on 2026-10-20 (it was video-notes-app). The Python package is `rot2gold`, the command `r2g`, the database `data/r2g.sqlite`; the code is on GitHub at `MarcoSburlino/rot2gold` (public).

### Local web UI on 127.0.0.1:8740

`r2g ui` starts a small web server and opens the browser at `http://127.0.0.1:8740`.

- **Stack:**
  - FastAPI and uvicorn, with HTML rendered on the server by Jinja2.
  - Plain HTML forms, plus a few lines of JavaScript for live run progress, which arrives over Server-Sent Events (SSE). Phase 1 needed nothing more, so htmx (planned) isn't used; add it, saved locally rather than from a CDN, only if a later screen needs it.
- **Why a web UI:**
  - It's the same Python as the pipeline, so the app calls the pipeline's functions directly.
  - There is no Node build step and nothing to package.
  - A desktop app (Tauri, Electron) would add Rust or Node toolchains and installers, for a single user. GTK would mean learning a UI toolkit.
- **Why 127.0.0.1:** it's the loopback address, reachable only from this laptop. Binding to `0.0.0.0` would expose the app to anyone on the same Wi-Fi.
- **Why 8740:** Marco's other projects use 3000, 3001, 5173, 1420/1421, 2020–2024, 3070, 5434, 8000, 8080, 8081, 8100 and 8888. 8740 is free. It's set in `config.toml` (`[app] port`) and noted in `AGENTS.md`.
- **No systemd service.** A service would run all the time on a laptop that is often asleep. The app starts on demand instead. `r2g install-launcher` adds a GNOME `.desktop` entry. `r2g ui` reuses an already running copy and writes output to `data/logs/ui.log` when started without a terminal.
- **Local request checks.** Every request must have the configured loopback Host header; writes must also have an Origin or Referer from that same local address. This blocks DNS rebinding and cross-site form posts.

### Functions, not printed output

The stages become functions that the app imports. The other option, wrapping the CLI, would mean parsing its printed output. That breaks on any change of wording, and it can't report structured errors.

- Each stage takes the ids it should work on and a `report(event)` callback, instead of printing.
- Stages raise typed errors (`errors.py`): `Blocked`, `CookiesNeeded`, `DownloaderOutdated`, `UsageLimit` and `LockHeld`. The CLI turns them into messages and exit codes. The UI turns them into banners that say what to do next.
- Every current `r2g` command keeps working.

### A run is its own process

Extract starts `r2g extract --conn <ids> --origin app` as a child process. The run writes its progress to SQLite (`run_events`), and the UI streams those rows to the browser over SSE.

- Closing the browser tab or restarting the server doesn't kill a run that may take an hour.
- A run started in a terminal (`r2g extract`) shows up live in the UI the same way.
- There is one code path for both.

### Lock: r2g.lock in the data folder

`flock` is a lock the kernel keeps on an open file (Linux and macOS; Windows: `msvcrt.locking` on one byte far past the text, because Windows also blocks reading a locked range). Only one process can hold it, and it is released the moment that process exits, even after a crash or `kill -9`. So there is never a stale lock to clean up by hand.

- The holder writes `{pid, run_id, origin, started}` into the file. That way the other side can say who holds it: "a terminal run (pid 1234), started 10:02, is in progress".
- Who takes the lock:
  - `r2g sync`, `fetch`, `process`, `run` and `extract` take it.
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
  - The agent loop, the tools (file edits, web search, `r2g` commands) and the prompts are identical, so a note looks the same whichever backend wrote it.
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
  - `Bash(r2g pending *)`, `Bash(r2g done *)`, `Bash(r2g skip *)`, `Bash(rg *)`, `Bash(find *)`.
  - No general shell and no git: the app commits, the AI doesn't.
- **What Anthropic's docs said on 2026-10-19:**
  - `claude -p` and the Agent SDK still draw from subscription limits. The planned separate credit was paused on 2026-06-15.
  - Since 2026-10-07, Max and Team plans also get monthly API credits. Pro doesn't.
  - The API key in the child environment selects API billing over the plan login.
  - Sources: support.claude.com articles 15036540 and 11145838, and code.claude.com/docs/en/headless.
- Codex was deferred here on 2026-10-19; on 2026-10-21 Codex CLI, Gemini CLI and local models were added for the open-source release (see "AI providers" below).

### Principle change: API keys allowed here

Marco's rule so far was "AI reasoning runs only through Marco's subscriptions, no API keys". **This project may also use an API key, if Marco chooses it in Settings.** The subscription stays the default.

The exception is for this project only. It is recorded here, in `AGENTS.md`, in `spec.md` and in the brain's `Projects/rot2gold.md`. Marco's global rules don't change.

### First-run setup (2026-10-21)

Until a vault is chosen (`config.is_set_up()`), every page redirects to `/setup` (the middleware leaves `/setup*`, `/static/`, `/healthz` and `/quit` open). `r2g` with no command opens the app, so a new user lands there.

- **The page** (`setup.html`, `setup.js`, logic in `firstrun.py`): six numbered steps. (1) What's installed: each AI tool, Tesseract (with the install command for this system), ffmpeg. (2) The vault: those Obsidian lists in its own `obsidian.json` (Linux native, Flatpak and Snap, macOS, Windows) or any folder, with a folder browser (`/setup/dirs`, folder names only); the app's folder name (default `Rot2Gold`); Git commits on or off. (3) The data folder, outside the vault, with free space. (4) The AI provider, with each one's status, Claude's account, the local server and model (suggested from `/setup/models`), an optional API key (to the keychain) and the note language. (5) OCR languages from what Tesseract has. (6) An optional first collection and the browser for its cookies. Then "Add to my app menu".
- **Saving** (`firstrun.validate`, `firstrun.save`): only the answered keys are written into the user's config.toml, so everything else stays. The vault layout is rewritten only on the first run or when a folder name is typed: an empty name keeps a custom layout like Marco's. A changed data folder can move the database (SQLite backup), media and logs, then delete the old copies. Then `vault.prepare()`, the collection, the launcher.
- **Restart:** the folders are read at start-up (`config.DATA`, …), so after saving, the server stops and `serve()` runs itself again with `os.execv`. The page waits for a new `BOOT_ID` from `/setup/status` (the process id stays the same through exec) and then offers "Open Rot2Gold". Before setup the server logs to the temp folder, so no data folder is created before one is chosen.
- **Terminal:** `r2g setup` asks the same questions; `r2g setup --check` prints where things are and what's installed (used by CI).
- **Run setup again:** Settings → About lists where things are and links to `/setup`, which then starts from the current config.

### Linux, macOS and Windows (2026-10-21)

- **Stop:** a run starts in its own process group (`start_new_session`; Windows: `CREATE_NEW_PROCESS_GROUP`). Stop sends SIGINT to the group; on Windows CTRL_BREAK, which `cli.main` turns into the same KeyboardInterrupt. Agents get SIGINT to end their turn; Windows can only end them (`ai.base.interrupt`).
- **Text encoding:** on Windows `cli.main` re-runs itself with `PYTHONUTF8=1`, so every file is read and written as UTF-8.
- **ffmpeg** from PATH or the copy bundled with `imageio-ffmpeg` (`tools.ffmpeg`), also passed to yt-dlp; the audio check uses PyAV instead of ffprobe. **Tesseract** from `[ocr] tesseract`, PATH or the usual install places (`tools.tesseract`).
- **Launcher** (`launcher.py`): a `.desktop` entry on Linux, `~/Applications/Rot2Gold.app` on macOS (a shell script, `Info.plist`, an `.icns` made with Pillow), a Start menu shortcut on Windows (PowerShell, `.ico` made with Pillow).
- **Cookies from any browser** yt-dlp supports: `connections.cookie_browser` (schema v9; existing rows keep `firefox`) with the optional profile in `firefox_profile`. On Windows, Chrome-based browsers lock their cookies, so the dialog suggests Firefox.
- **Firefox profiles** are found in the Linux, Flatpak, macOS and Windows folders.
- Paths go through `pathlib`; vault paths in the database and prompts use `/` on every system.

### AI providers (2026-10-21)

`[ai] provider` picks who writes notes and finds ideas. The prompts and rules are the same for all agents.

| Provider | How it runs | Tools | Login |
|---|---|---|---|
| `claude` | `claude -p` (`ai/claude_cli.py`) | `--allowedTools` list above | plan login, or Anthropic key |
| `codex` | `codex exec --json --output-schema` (`ai/codex_cli.py`) | sandbox `workspace-write` (writes only in the vault and `--add-dir`s, no network for commands) plus its web search (`-c web_search="live"`) | `codex login`, or `CODEX_API_KEY` from the keychain |
| `gemini` | `gemini -p --output-format stream-json` (`ai/gemini_cli.py`) | a `--policy` file allowing file tools, web search, `r2g pending/done/skip` and `rg`; anything else needs approval, which headless mode refuses | Google sign-in, or `GEMINI_API_KEY` |
| `local` | `direct.py` with `ai/local.py` (OpenAI-compatible `/v1/chat/completions`, `response_format` JSON schema) | none: the app sends the post data and writes the note, hub and quotes itself | optional server key |

- Codex gets the strict form of the report schema (`base.strict`). Gemini has no schema flag: the prompt asks for the JSON report and the app checks its keys.
- Plan-usage stops (`stop_at_plan_usage`) apply only to Claude on a subscription, the only provider that reports it. The others stop on their own limit errors.
- Direct-mode notes have the same format, without checked claims (no web search) or links to other notes. Small models skip posts too eagerly, so a skip counts only for a post with almost no speech or text (`direct.has_words`).
- Tested 2026-10-21: one real note each with Codex (ChatGPT login) and with llama.cpp's `llama-server` serving Qwen2.5 1.5B; Gemini CLI only up to its auth check (no Google login on this laptop).

### API keys in the system keychain

Keys are stored with the `keyring` library: the Secret Service (GNOME Keyring) on Linux, Keychain on macOS, Credential Manager on Windows; service `rot2gold`, one user per provider (`anthropic`, `openai`, `gemini`, `local`). Until 2026-10-21 the Anthropic key used `secret-tool` directly; Marco had none stored, so nothing was moved.

- **Why not a `chmod 600` file in `~/.config/`:**
  - The file would still be plain text on disk, visible to backups and `rg`.
  - Marco's rules already forbid agents from opening `api-key` files.
  - A keyring entry has no file to read by accident.
- **Entering the key:** the Settings page passes it to the keychain in-process, never as a command-line argument (arguments are visible to every user in `ps`). Afterwards the page shows only "key set" or "not set".
- **No keyring:** without one (for example over SSH, with no desktop session), API mode stops with "keyring unavailable". It never falls back to a file.

### Review and undo after commits

Each batch of notes is committed on its own, and Git is the review and undo tool.

- **Review:** `git show` and Obsidian.
- **Undo:** an "Undo this run" button and `r2g undo` revert a run's commits, re-open its noted posts if their note files are gone, and clear its ideas, learnings and events checks. Undo refuses staged or conflicting changes and is itself a locked, recorded run.

A true "hold before commit" mode would need a staging copy of `commonplace.md` and `quotes.md`, which every batch also edits. It is not built: undo provides review after the fact without a second commit path.

### Settings overlay

Defaults ship in the package (`src/rot2gold/resources/defaults.toml`). The user's own `config.toml` (in the system config folder: `~/.config/rot2gold/` on Linux) holds only what they changed; it is merged over the defaults section by section. Settings validates the editable preferences and writes them into that file atomically (`settings.py`, `config.write_user`). The API key stays in the keyring. Until 2026-10-21 the defaults were a tracked `config.toml` and preferences were in `data/settings.json`; Marco's values were moved into his `~/.config/rot2gold/config.toml` by hand.

## Data model (schema v9)

All state stays in `data/r2g.sqlite`.

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
- Schema v5 lets `batches.kind` be `delete` (a deleted idea). SQLite can't change a CHECK rule, so v4→v5 rebuilds `batches` with the same rows in one transaction, after a one-time backup `data/r2g.sqlite.bak-v4`. `runs.kind` gains `delete`.
- Schema v6 (2026-10-20) adds learnings: `posts.learnings_checked_at`, `runs.learnings_created`, `runs.learnings_updated`, and `batches.learned` (the posts a batch checked for learnings, so Undo clears just those). Additive, after a one-time backup `data/r2g.sqlite.bak-v5`.
- Schema v9 (2026-10-21) adds `connections.cookie_browser` (default `firefox`): cookies can come from any browser yt-dlp supports.
- Schema v8 (2026-10-21) stores `images.path` relative to the data folder (`media/<id>/…`) instead of the repository (`data/media/<id>/…`), so the data folder can live anywhere. One-time backup `r2g.sqlite.bak-v7` first.
- Schema v7 (2026-10-20) adds events the same way: `posts.events_checked_at`, `runs.events_created`, `runs.events_updated`, and `batches.events_seen`. Additive, after a one-time backup `data/r2g.sqlite.bak-v6`.

### Changes to `posts`

- `platform`, default `tiktok`.
  - TikTok ids stay bare, matching `post_id` in the existing notes.
  - Other platforms use `<platform>:<id>` (e.g. `yt:abc123`), so ids can't collide.
- `ideas_checked_at`: when the ideas pass last considered the post's note for ideas. NULL means it still has to.
- `learnings_checked_at`: the same for learnings. NULL means it still has to, whatever the note's age.
- `events_checked_at`: the same for events, also whatever the note's age.

### Status values

They stay `new → fetched → processed → done | skipped`, so existing rows and commands keep working. The UI labels them **listed, fetched, processed, noted, skipped**.

### Migration

It runs once, on the first start of the new code:

1. Copy `data/r2g.sqlite` to `data/r2g.sqlite.bak-v1`.
2. Add the new tables and columns.
3. Create the connection "Material" from `config.toml`'s `collection_url`, and link all existing posts to it.
4. Move the `meta.cookies` flag into that connection.
5. Remove `collection_url` from `config.toml`. From then on, connection URLs live only in the (gitignored) database.

`PRAGMA user_version` records the schema version. The plain `r2g sync` command then syncs every connection.

### Deleting a connection

This removes the connection and its link rows. Posts, media and brain notes stay. The confirmation says how many posts belonged only to that connection.

## Sources (pluggable)

`src/rot2gold/sources/base.py` defines what every platform provides:

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
   2. Run one `claude -p` with `resources/prompts/write-notes.md` and the batch's ids, inside the vault.
   3. Check every post of the batch in the database: either `done` with a `note_path` that exists, or `skipped`.
   4. Run `brain-index`, then `brain-index --check`.
   5. Stage only the paths that changed since the snapshot *and* are under `Resources/commonplace/` or are generated indexes. Commit as `agent: video notes batch (run N)`. Anything else that changed (Obsidian, another agent) stays unstaged.
6. **Ideas, learnings and events pass.** Batches of up to 25 notes: those marked done on or after `[ideas] since` and not checked for ideas, then notes of any age not checked for learnings or events, each tagged with what to look for. One `claude -p` call per batch with `prompts/ideas.md` (see `ideas.md`). Each completed batch is indexed, checked and committed from `Inbox/ideas/`, `Inbox/learnings/`, `Inbox/events/` and the indexes as `agent: ideas pass N (run N)`.
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
- **Settings.** Batch size, notes per run and model are set in Settings and stored in the user's `config.toml`.

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

Redesigned 2026-10-19 (Marco's request: Ideas and Videos as the main pages, collections in a sidebar, Settings as a card, runs linked to collections). Simplified 2026-10-20 (Marco: "the app is kind of complicated to use"): one Extract button, plain words instead of pipeline terms, technical detail folded away, no dry-run step in the app. Restyled 2026-10-20 from Marco's Claude Design project: always dark, near-black with one gold, Outfit / Instrument Sans / JetBrains Mono bundled in the app, the design's horizon app icon (`static/icon.png`, used as the browser tab icon and the GNOME launcher icon); the screens and their structure did not change. Visual rules: `.claude/skills/design-system/` — read it before any UI change.

**App shell.** A sidebar on every page (a top bar plus drawer under 768 px):
- Ideas, Learnings, Events and Videos with counts, and History.
- **Collections**: one row per connection: its name (→ its videos), "N videos" (plus "M waiting for a note" when some are), and its last extract in words ("Last extract yesterday: 7 notes, 0 ideas", → the run). The ⋯ button opens a card with links (its videos, its history, TikTok), Name and Link, an "Advanced" fold (Firefox cookies and profile, backup video links), "Extract only this one" when there are several collections, and Remove. + adds one: link and optional name; cookies under "Private collection?". The platform choice appears only once a second platform exists.
- **Extract new videos**: one button that reads every collection, with a sentence saying what it does. Hidden while a run holds the lock.
- A live run widget while a run holds the lock (from the app or a terminal): what it's doing, the last log line, See progress and Stop.
- ⚙ **Settings** opens a card of fixed size (only the tab's content scrolls, the tabs stay put) with tabs: General (AI backend, models, notes per run; batch sizes, plan-usage stop and API budget under Advanced; the API key folded unless the API backend is picked), Usage (plan windows), About (downloader versions and update, brain path, Firefox profiles). Settings forms return to the page you were on with the card reopened. `/settings` renders the same panel as a page without JavaScript.
- Quit.

**Ideas** (`/`, `/ideas`, `/ideas/<name>`): the home page. Status chips (only statuses that have ideas) and search; from 1100 px the list sits beside a reading pane with the selected idea. Each idea shows its **source strip**: the supporting videos as tiny 9:16 frames (the signature element), linked to their videos in the reading pane. When notes under the themes haven't been checked for ideas, a banner offers "Check them": a card that runs `r2g ideas rebuild` (all themes, or some under a fold) and writes straight to the brain — Undo is the safety net, so the app has no dry-run step (the CLI keeps `--dry-run`, and old previews stay reachable from their run page). Idea files are read from `~/Projects/brain/Inbox/ideas/`, so Marco's edits show up; status is changed in Obsidian.

**Learnings** (`/learnings`, `/learnings/<name>`, added 2026-10-20): the same page as Ideas (`ideas.html`, labels from `KIND_PAGES` in `web/app.py`) for `~/Projects/brain/Inbox/learnings/`: what the videos taught, combined across the videos that say the same thing. While notes aren't checked for learnings, a banner says the next Extract checks them, 25 at a time, and offers "Check them now" (the same rebuild card). Its ⋯ menu holds "Delete learning…", which works like deleting an idea.

**Events** (`/events`, `/events/<name>`, added 2026-10-20): the same page for `~/Projects/brain/Inbox/events/`: things the videos report (news, releases, history) or announce (conferences, festivals, launches). Each row shows its date and place in mono. The list is grouped **Coming up** (soonest first) until an event's last day (`until:`, else `when:`) has passed (with only a month or year, until that period begins), then **Past** (most recent first), then **No date**; the chips filter by those groups instead of by status. An upcoming event with a full date has **Add to calendar**, which downloads an `.ics` file (`/events/<name>/calendar.ics`, built by `ideas.calendar_file`). Same unchecked-notes banner and ⋯ menu as Learnings.

**Deleting an idea** (2026-10-20): the ⋯ menu at the top right of the reading pane holds "Delete idea…", which opens a card. It deletes the idea file and removes `## Related ideas` links to it from other ideas. Ticking "Also delete its videos" also deletes those video notes from the brain and their lines in `commonplace.md`, except videos that support another idea or learning (listed as kept). List links to it in any idea, learning or event (`## Related ideas`, `## Learnings behind it`, `## Use it`, `## Related learnings`, `## Learnings it shows`, `## Related events`, …) are removed. Deleted videos stay in the database as `skipped` ("deleted by you with the idea …"), so Extract never writes them again; their media in `data/media/` stays. Links to them inside other video notes are left as unresolved links. It runs as a `delete` run with one brain commit, so History lists it and Undo restores the files and sets the videos back to noted (code: `src/rot2gold/delete.py`, `undo.py`).

**Videos** (`/videos`): rows with a 9:16 thumbnail, title, description, creator, date and type; a status pill only when a video isn't noted. Chips only for groups that have videos (All · Waiting · Skipped), search, and a removable "In <collection>" filter when there are several collections. **Video detail** (`/videos/<id>`): header with thumbnail, title, Open in Obsidian and Open on TikTok; the note (rendered with raw HTML switched off, wikilinks to app pages or Obsidian); a rail with frames or slides, **Ideas from this video**, **Learnings from this video**, **Events in this video** (only when there are some), the text and speech read from the video, and folded details.

**History** (`/runs`, `/runs?conn=<id>`, `/runs/<id>`): every run as a row with a plain title ("Extract · Material", "Ideas, learnings and events from older notes", "Downloader update", "Deleted a learning") and one sentence of what it did ("Checked 111 videos, wrote 7 notes, 2 new learnings."); a pill only when it didn't end ok. A run page leads with that sentence (or the live stages and last log line while running), Stop or Undo (a confirmation card), and folds the Log and the Details (counts, collections, AI and its API value, brain commits, plan windows, batches). `/runs?kind=ideas` still works but isn't linked.

## Files

```
docs/app-spec.md           this file
src/rot2gold/resources/    rules, prompts, templates, starter notes, an example note, defaults.toml
docs/ideas.md              history of the ideas, learnings and events pass
docs/note-writing.md       history of the note-writing rules
src/rot2gold/
  db.py                    schema v7, migration, WAL                (changed)
  delete.py                delete an idea, learning or event and, optionally, its videos
  sync.py fetch.py process.py  ids, callbacks, typed errors        (changed)
  cli.py                   extract, ui, conn add|list|rm, lock      (changed)
  lock.py events.py errors.py
  extract.py               the Extract run
  runs.py                  shared lock, run row and final status
  notes.py                 note-writing batches
  firstrun.py              first-run setup: finding vaults, checks, validating and saving the answers
  vault.py                 the app's folders, templates and starter notes in the vault; the "Where things are" block of every prompt
  ideas.py                 ideas, learnings and events pass; reading their notes; event dates and .ics
  brain.py                 git snapshot, staged commit, brain-index, front matter, Obsidian links
  secrets.py               API keys in the system keychain (keyring)
  direct.py                direct mode for local models: JSON answers, the app writes the files
  ai/                      the providers: claude_cli, codex_cli, gemini_cli, local; base (Result, strict schemas)
  settings.py              validated preferences, saved into the user's config.toml
  paths.py                 where the config, data and bundled resources live (platformdirs)
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
   - Schema v2 and the migration, lock, events, sources, `extract.py`, the subscription backend, batch commits, `r2g extract`.
   - A minimal UI: the Connections screen and the run panel.
   - Done when Marco adds a connection, presses Extract, and new posts become committed notes, as in the run of 2026-10-15.
2. **Browse.** The Videos and Video detail screens.
3. **Ideas.** The ideas pass in Extract, theme-based rebuilds, dry-run previews, and the Ideas screen. Migrating the 14 first-run idea files remains a separate brain change.
4. **API backend (built).** Settings, keyring, full Claude tool set, budget caps, usage per run and per batch.
5. **Extras (built).** Undo this run, a `.desktop` launcher, the Update downloaders button and Quit. Optional hold for review and a Codex note-writing backend are deferred for the reasons above.

## Acceptance checks

- The migration, run on a copy of the database, keeps all 104 posts (101 done, 3 skipped), every one linked to "Material".
- With a terminal `r2g extract` running, Extract in the UI reports that run. After `kill -9` of the terminal run, the lock is free at once.
- A new post in Material is the only one fetched and written up. The brain commit contains only its note, the hub, quotes and the indexes. `.obsidian/graph.json` stays unstaged.
- A post saved in two connections is processed once and listed under both.
- With a wrong Firefox profile or a dead URL list, the UI shows the matching message and next step.
- Running the ideas pass twice on the same notes creates and updates nothing the second time.
- In API mode: the keychain holds the key (service `rot2gold`, user `anthropic`), a batch reports its cost, and a missing key gives a clear error.
