# Rot2Gold

Turns the posts Marco saves on TikTok into notes in his brain (`~/Projects/brain/Resources/commonplace/`), plus ideas, learnings and events found across notes (`~/Projects/brain/Inbox/ideas/`, `learnings/`, `events/`). Named Rot2Gold on 2026-10-20 (it was video-notes-app).

Two parts, one repo:

- **The pipeline, `r2g`** (built, working): lists a collection, downloads each post, runs OCR (Tesseract) and speech-to-text (faster-whisper), and stores everything in SQLite. An agent then writes one note per post.
- **The app** (Phases 1–5 built): a local web UI for Extract, browsing, Settings, usage, undo and updates (`docs/app-spec.md` → "Phases").

## Docs

- `docs/spec.md`: the pipeline, its data and every decision, with test results.
- `docs/app-spec.md`: the app: goals, decisions and why, data model, Extract steps, screens, phases.
- `docs/note-writing.md`: how to write a note for a processed post. Follow it when asked to process posts.
- `docs/ideas.md`: rules for the ideas pass. Every agent and backend follows it.
- `prompts/`: the prompts the app gives `claude -p` (one note-writing batch, one ideas pass).

## Rules

- AI reasoning runs through Marco's Claude subscription (Claude Code, `claude -p`) by default. The app may also use an Anthropic API key, by Marco's choice in Settings (decided 2026-10-19; this exception is for this project only). No local LLMs; local utility models (speech-to-text, OCR) are fine.
- The API key lives only in the GNOME keyring (`secret-tool`, `service rot2gold`, `account anthropic`). Never in a file, a `config.toml`, Git, logs or notes. Never print it.
- Never fetch or store captions, hashtags or comments.
- Connection (collection) URLs live only in the database (`<data folder>/r2g.sqlite`, `r2g conn list`), never in Git.
- One pipeline run at a time: every command that runs the pipeline takes the lock `<data folder>/r2g.lock`. Never delete the lock file by hand; the kernel releases it when its process ends.
- The web UI listens on `127.0.0.1:8740` only, never `0.0.0.0`.
- UI work follows the design system in `.claude/skills/design-system/` (colours, type, spacing, components, motion): always dark, black and one gold. Fonts are bundled in `src/rot2gold/web/static/fonts/`; never load fonts or scripts from other hosts. Keep templates and CSS readable: one element or rule per line.
- Vault writes (`brain.py`): run the user's after-write commands (`[vault] after_write`; for Marco's brain, `brain-index` and `brain-index --check`), then, if the vault uses Git, commit with `agent: ` messages, staging only the paths that changed. Never `git add -A`, never `.obsidian/`, never push the vault.
- `data/` and `.venv/` are gitignored. Secrets never go into notes or Git.
- The repo is **public** on GitHub (`git@github.com:MarcoSburlino/rot2gold.git`, branch `main`). Before every push, check the diff for secrets and personal data (keys, tokens, cookies, Marco's TikTok handle or collection links, his email). Tests use made-up URLs. Commits use the GitHub no-reply address set in this repo's Git config.
- Settings: bundled defaults in `src/rot2gold/resources/defaults.toml`, overlaid by the user's `config.toml` in their config folder (`paths.config_file()`; `R2G_CONFIG` overrides it). The app writes only that user file (setup and Settings). The data folder (media, database, logs, lock) is `[storage] data_dir`; Marco's is still this repo's `data/`. Tests use their own config (`tests/conftest.py`).
- Fedora: `dnf`, not `apt`.

## How to run it

```
r2g ui             # the app at http://127.0.0.1:8740 (Ctrl+C stops the server, not a running Extract)
r2g extract        # the whole pipeline for every connection, as one run; --conn 1,2  --max-notes N  --no-notes  --no-ideas
r2g ideas list     # idea notes by support, status, name and title
r2g ideas themes   # themes with total and unchecked note counts
r2g ideas pass     # new unchecked notes; --conn 1,2  --dry-run
r2g ideas rebuild  # unchecked notes under themes; --themes "Name,Other"  --limit N  --dry-run
r2g conn list      # connections; add <url> [--name N] | edit <id> | rm <id> | links <id> < urls.txt
r2g runs           # recent runs with counts and AI usage
r2g undo <run_id> [--yes]  # revert a run's brain commits and reopen its posts
r2g update-downloaders    # upgrade yt-dlp and gallery-dl in the venv
r2g install-launcher      # add the GNOME launcher; uninstall-launcher removes it
r2g run 25         # sync + fetch + process up to 25 posts, without note writing
r2g status         # counts by status and skip reason; connections; what is running
r2g pending 10     # processed posts waiting for a note
r2g done <id> <note-path>   |   r2g skip <id> "<reason>"
.venv/bin/python -m pytest -q tests   # tests (temporary folders only; never the real database or brain)
```

- Setup:
  ```
  uv venv --python 3.14 .venv
  uv pip install --python .venv/bin/python -e '.[dev]'
  ln -sfn ~/Projects/rot2gold/.venv/bin/r2g ~/.local/bin/r2g
  ```
  The venv records its own absolute path, so after moving or renaming this folder, delete `.venv` and run the setup again.
  Tesseract comes from `sudo dnf install tesseract tesseract-langpack-ita tesseract-langpack-spa` (fallback: `docs/spec.md`).
- When TikTok downloads start failing: `uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl`.
- Every stage skips finished work. Stop any command and rerun it.
- Whisper model benchmark: `.venv/bin/python scripts/whisper_bench.py <out-dir> data/media/<id>/audio.wav ...`. Run it on fetched posts before `r2g process`, which deletes the audio.

When asked to process posts, follow docs/note-writing.md.

## Brain

Project note: ~/Projects/brain/Projects/rot2gold.md. Add a log entry there at the end of a session that changed something.
